"""
@author: Zhang Shuo
"""

# 导入sys库
import sys 
# 临时添加本地库（添加import库的搜索路径），在列表的任意位置添加目录，新添加的目录会优先于其它目录被import检查
sys.path.insert(0, '../../main/') 

# 调库
import tensorflow as tf 
## 调用tensorflow开发工具
import numpy as np 
## 调用科学计算工具 
import matplotlib.pyplot as plt 
## 调用python的画图功能库
import scipy.io 
## 调用物理常量/单位库、常用的输入输出函数
from scipy.interpolate import griddata 
## 调用griddata差值函数（非规则网格的数据差值）
import time 
## 调用时间日期函数
from itertools import product, combinations 
## itertools是用于迭代工具的标准库，itertools.product计算多个可迭代对象的笛卡尔积，itertools.combinations生成可迭代对象的所有长度为r的组合
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
## mpl_toolkits是matplotlib的绘图工具包，mpl_toolkits.mplot3d用于绘制和可视化三维图形
from plotting import newfig, savefig
## plotting可以结合各种视觉元素和工具创建可视化图形的库
from mpl_toolkits.axes_grid1 import make_axes_locatable
## axes_grid1是辅助类几何工具，可以用于显示多个图像
import matplotlib.gridspec as gridspec
## gridspec是专门指定画布中的子图位置的模块

# 设置随机数种子
np.random.seed(1234)
tf.set_random_seed(1234)

# 定义PINN的类（类是一种数据类型，代表着一类具有相同属性和方法的对象的集合）
class PhysicsInformedNN:
  #定义用来初始化神经网络参数项的函数
  def __init__(self, x, y, t, u, v, layers):
    
    ## 数组的组合拼接，1表示按列拼接，X表示自变量的矩阵
    X = np.concatenate([x, y, t], 1)
    
    ## 0表示返回矩阵中每一列的最小值，1表示返回每一行的最小值，即表示
    self.lb = X.min(0)
    self.ub = X.max(0)
    
    ## 保存类的自变量矩阵
    self.X = X
    
    ## 分别保存类的自变量 X[：,0:1]取所有数据的第m到n-1列数据，即含左不含右
    self.x = X[:,0:1]
    self.y = X[:,1:2]
    self.t = X[:,2:3]
    
    ## 分别保存类的因变量
    self.u = u
    self.v = v
    
    ## 保存类的NN层数
    self.layers = layers
   
    ## 定义神经网络的参数？
    self.weights, self.biases = self.initialize_NN(layers)
    
    ## 初始化参数，定义变量类型，0.0表示定义变量初值，dtype表示创建一个数据类型对象
    self.lambda_1 = tf.Variable([0.0], dtype=tf.float32)
    self.lambda_2 = tf.Variable([0.0], dtype=tf.float32)
    
    ## tf.Session用来创建一个新的tensorflow会话
    ## tensorflow的计算图只是描述了计算执行的过程，没有真正执行计算，真正的计算过程是在tensorflow的会话中进行的
    ## Session提供了求解张量，执行操作的运行环境，将计算图转化为不同设备上的执行步骤。包括创建会话（tf.Session）、执行会话（sess.run）、关闭会话（sess.close）
    ## tf.ConfigProto作用是配置tf.Session的运算方式，比如GPU运算或CPU运算
    ## allow_soft_placemente表示当运行设备不满足时，是否自动分配GPU或CPU
    ## log_device_placement表示是否打印设备分配日志
    self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True,log_device_placement=True))
    
    ## tf.placeholder是常用的处理输入数据的工具，允许在定义计算图时创建占位符节点，tf.placeholder(dtype,shape=none,name=none)
    ## dtype指定占位符的数据类型，如tf.float32,tf.int32
    ## shape指定占位符的形状，如不指定，可接受任意形状的输入数据
    ## name是给占位符名称指定一个可选的名称
    self.x_tf = tf.placeholder(tf.float32, shape=[None, self.x.shape[1]])
    self.y_tf = tf.placeholder(tf.float32, shape=[None, self.y.shape[1]])
    self.t_tf = tf.placeholder(tf.float32, shape=[None, self.t.shape[1]])
    
    self.u_tf = tf.placeholder(tf.float32, shape=[None, self.u.shape[1]])
    self.v_tf = tf.placeholder(tf.float32, shape=[None, self.v.shape[1]])
    
    ## 构建神经网络的输入输出关系？
    self.u_pred, self.v_pred, self.p_pred, self.f_u_pred, self.f_v_pred = self.net_NS(self.x_tf, self.y_tf, self.t_tf)

    ## 定义损失函数的计算关系
    self.loss = tf.reduce_sum(tf.square(self.u_tf - self.u_pred)) + \
                tf.reduce_sum(tf.square(self.v_tf - self.v_pred)) + \
                tf.reduce_sum(tf.square(self.f_u_pred)) + \
                tf.reduce_sum(tf.square(self.f_v_pred))

    ## 定义优化方法
    ## tf.contrib.opt.ScipyOptimizerInterface是tensorflow的模块，提供将Scipy优化器与tensorflow集成的接口，可使用Scipy中的优化算法来优化Tensorflow模型中的变量
    ## L-BFGS-B表示优化方法
    ## maxiter定义最大迭代次数，int
    ## maxfun定义函数计算的最大数量，int
    ## maxcor定义有限内存矩阵的最大可变度量校正数（有限内存BFGS方法不存储完整的hessian，而是使用多项校正数来近似），int
    ## maxls定义最大的线性搜索步数，int，默认值20
    ## ftol表示当f^k-f^[(k+1)/max[f^k,f^(k+1),1]]小于ftol值时，迭代停止
    self.optimizer = tf.contrib.opt.ScipyOptimizerInterface(self.loss, 
                                                            method = 'L-BFGS-B', 
                                                            options = {'maxiter': 50000,
                                                                       'maxfun': 50000,
                                                                       'maxcor': 50,
                                                                       'maxls': 50,
                                                                       'ftol' : 1.0 * np.finfo(float).eps})
    
    ## 引入adam优化算法：是一个选取全局最优点的优化算法，引入了二次方梯度修正，来最小化损失函数
    self.optimizer_Adam = tf.train.AdamOptimizer()
    self.train_op_Adam = self.optimizer_Adam.minimize(self.loss) 
    
    ## 初始化模型的参数
    init = tf.global_variables_initializer()
    self.sess.run(init)

    # 定义一个用来初始化神经网络中各参数值的函数
    def initialize_NN(self, layers):  
      weights = []
      biases = []
      num_layers = len(layers)  ## num_layers为层向量的长度，即为神经元的层数
      for l in range(0,num_layers-1):
        W = self.xavier_init(size=[layers[l], layers[l+1]])  ## xavier_init()是随机初始化参数的分布范围，此处是初始化每两层之间的权重参数w，是一个l层（m个输入）到l+1层（n个输出）的m*n矩阵
        b = tf.Variable(tf.zeros([1,layers[l+1]], dtype=tf.float32), dtype=tf.float32)  ##  tf.zeros()表示生成全为0的tensor张量，此处是初始化每层的偏移参数b,从第l+1层开始（n个输出）是一个1*n的向量，初始值为0
        weights.append(W)
        biases.append(b)  ## append表示在变量末尾增加元素，此处即把每次循环的w，b都存进空矩阵weight，biases中，即weight,biases为所有层之间的权重和偏移参数的矩阵
      return weights, biases
    
    # 定义一个标准差函数
    def xavier_init(self, size):
      in_dim = size[0]
      out_dim = size[1]        
      xavier_stddev = np.sqrt(2/(in_dim + out_dim))
      return tf.Variable(tf.truncated_normal([in_dim, out_dim], stddev=xavier_stddev), dtype=tf.float32)

    








  









