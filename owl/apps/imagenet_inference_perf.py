import math
import sys
import time
import numpy as np
import owl
from owl.conv import *
import owl.elewise as ele
from imageio import ImageNetDataProvider

num_gpu = 1
one_gpu_id = 0
gpu_array = []

class AlexModel:
    def __init__(self):
        self.weights = []
	self.weightsdelta = []
        self.bias = []
        self.biasdelta = []
	self.conv_infos = [
            conv_info(0, 0, 4, 4), # conv1
            conv_info(2, 2, 1, 1), # conv2
            conv_info(1, 1, 1, 1), # conv3
            conv_info(1, 1, 1, 1), # conv4
            conv_info(1, 1, 1, 1)  # conv5
        ];
        self.pooling_infos = [
            pooling_info(3, 3, 2, 2, pool_op.max), # pool1
            pooling_info(3, 3, 2, 2, pool_op.max), # pool2
            pooling_info(3, 3, 2, 2, pool_op.max)  # pool5
        ];
        self.num_layers = 20
        self.num_weights = 8

    def init_random(self):
        self.weights = [
            owl.randn([11, 11, 3, 96], 0.0, 0.01),
            owl.randn([5, 5, 96, 256], 0.0, 0.01),
            owl.randn([3, 3, 256, 384], 0.0, 0.01),
            owl.randn([3, 3, 384, 384], 0.0, 0.01),
            owl.randn([3, 3, 384, 256], 0.0, 0.01),
            owl.randn([4096, 9216], 0.0, 0.01),
            owl.randn([4096, 4096], 0.0, 0.01),
            owl.randn([1000, 4096], 0.0, 0.01)
        ];
	self.weightsdelta = [
            owl.zeros([11, 11, 3, 96]),
            owl.zeros([5, 5, 96, 256]),
            owl.zeros([3, 3, 256, 384]),
            owl.zeros([3, 3, 384, 384]),
            owl.zeros([3, 3, 384, 256]),
            owl.zeros([4096, 9216]),
            owl.zeros([4096, 4096]),
            owl.zeros([1000, 4096])
        ];
        self.bias = [
            owl.zeros([96]),
            owl.zeros([256]),
            owl.zeros([384]),
            owl.zeros([384]),
            owl.zeros([256]),
            owl.zeros([4096, 1]),
            owl.zeros([4096, 1]),
            owl.zeros([1000, 1])
        ];
        self.biasdelta = [
            owl.zeros([96]),
            owl.zeros([256]),
            owl.zeros([384]),
            owl.zeros([384]),
            owl.zeros([256]),
            owl.zeros([4096, 1]),
            owl.zeros([4096, 1]),
            owl.zeros([1000, 1])
        ];

def print_training_accuracy(o, t, minibatch_size):
    predict = o.max_index(0)
    ground_truth = t.max_index(0)
    correct = (predict - ground_truth).count_zero()
    print 'Training error: {}'.format((minibatch_size - correct) * 1.0 / minibatch_size)
    sys.stdout.flush()

def train_one_mb(model, data, label, weightsgrad, biasgrad, dropout_rate):
    num_samples = data.shape[-1]
    num_layers = 20
    acts = [None] * num_layers
    sens = [None] * num_layers
    # FF
    acts[0] = data
    acts1 = conv_forward(acts[0], model.weights[0], model.bias[0], model.conv_infos[0])
    acts[1] = ele.relu(acts1)#(conv_forward(acts[0], model.weights[0], model.bias[0], model.conv_infos[0])) # conv1
    acts[2] = pooling_forward(acts[1], model.pooling_infos[0]) # pool1
    acts3 = conv_forward(acts[2], model.weights[1], model.bias[1], model.conv_infos[1]) # conv2
    acts[3] = ele.relu(acts3)#(conv_forward(acts[2], model.weights[1], model.bias[1], model.conv_infos[1])) # conv2
    acts[4] = pooling_forward(acts[3], model.pooling_infos[1]) # pool2
    acts5 = conv_forward(acts[4], model.weights[2], model.bias[2], model.conv_infos[2]) # conv3
    acts[5] = ele.relu(acts5)#(conv_forward(acts[4], model.weights[2], model.bias[2], model.conv_infos[2])) # conv3
    acts6 = conv_forward(acts[5], model.weights[3], model.bias[3], model.conv_infos[3]) # conv4
    acts[6] = ele.relu(acts6)#(conv_forward(acts[5], model.weights[3], model.bias[3], model.conv_infos[3])) # conv4
    acts7 = conv_forward(acts[6], model.weights[4], model.bias[4], model.conv_infos[4]) # conv5
    acts[7] = ele.relu(acts7)#(conv_forward(acts[6], model.weights[4], model.bias[4], model.conv_infos[4])) # conv5
    acts[8] = pooling_forward(acts[7], model.pooling_infos[2]) # pool5
    re_acts8 = acts[8].reshape([int(np.prod(acts[8].shape[0:3])), num_samples])
    acts9 = model.weights[5] * re_acts8 + model.bias[5] # fc6
    acts[9] = ele.relu(acts9)#(model.weights[5] * re_acts8 + model.bias[5]) # fc6
    mask6 = owl.randb(acts[9].shape, dropout_rate)
    acts[9] = ele.mult(acts[9], mask6) # drop6
    acts10 = model.weights[6] * acts[9] + model.bias[6] # fc7
    acts[10] = ele.relu(acts10)#(model.weights[6] * acts[9] + model.bias[6]) # fc7
    mask7 = owl.randb(acts[10].shape, dropout_rate)
    acts[10] = ele.mult(acts[10], mask7) # drop7
    acts[11] = model.weights[7] * acts[10] + model.bias[7] # fc8
    acts[12] = softmax_forward(acts[11].reshape([1000, 1, 1, num_samples]), soft_op.instance).reshape([1000, num_samples]) # prob
    # error
    sens[11] = acts[12] - label
    # BP
    sens[10] = model.weights[7].trans() * sens[11] # fc8
    sens[10] = ele.mult(sens[10], mask7) # drop7
    sens[10] = ele.relu_back(sens[10], acts[10]) # relu7
    sens[9] = model.weights[6].trans() * sens[10]
    sens[9] = ele.mult(sens[9], mask6) # drop6
    sens[9] = ele.relu_back(sens[9], acts[9]) # relu6
    sens[8] = (model.weights[5].trans() * sens[9]).reshape(acts[8].shape) # fc6
    sens[7] = pooling_backward(sens[8], acts[8], acts[7], model.pooling_infos[2]) # pool5
    sens[7] = ele.relu_back(sens[7], acts[7]) # relu5
    sens[6] = conv_backward_data(sens[7], model.weights[4], model.conv_infos[4]) # conv5
    sens[6] = ele.relu_back(sens[6], acts[6]) # relu4
    sens[5] = conv_backward_data(sens[6], model.weights[3], model.conv_infos[3]) # conv4
    sens[5] = ele.relu_back(sens[5], acts[5]) # relu3
    sens[4] = conv_backward_data(sens[5], model.weights[2], model.conv_infos[2]) # conv3
    sens[3] = pooling_backward(sens[4], acts[4], acts[3], model.pooling_infos[1]) # pool2
    sens[3] = ele.relu_back(sens[3], acts[3]) # relu2
    sens[2] = conv_backward_data(sens[3], model.weights[1], model.conv_infos[1]) # conv2
    sens[1] = pooling_backward(sens[2], acts[2], acts[1], model.pooling_infos[0]) # pool1
    sens[1] = ele.relu_back(sens[1], acts[1]) # relu1
    weightsgrad[7] = sens[11] * acts[10].trans()
    weightsgrad[6] = sens[10] * acts[9].trans()
    weightsgrad[5] = sens[9] * re_acts8.trans()
    weightsgrad[4] = conv_backward_filter(sens[7], acts[6], model.conv_infos[4])
    weightsgrad[3] = conv_backward_filter(sens[6], acts[5], model.conv_infos[3])
    weightsgrad[2] = conv_backward_filter(sens[5], acts[4], model.conv_infos[2])
    weightsgrad[1] = conv_backward_filter(sens[3], acts[2], model.conv_infos[1])
    weightsgrad[0] = conv_backward_filter(sens[1], acts[0], model.conv_infos[0])
    biasgrad[7] = sens[11].sum(1)
    biasgrad[6] = sens[10].sum(1)
    biasgrad[5] = sens[9].sum(1)
    biasgrad[4] = conv_backward_bias(sens[7])
    biasgrad[3] = conv_backward_bias(sens[6])
    biasgrad[2] = conv_backward_bias(sens[5])
    biasgrad[1] = conv_backward_bias(sens[3])
    biasgrad[0] = conv_backward_bias(sens[1])
    return acts[12]

def train_network(model, num_epochs = 100, minibatch_size=256,
        dropout_rate = 0.5, eps_w = 0.01, eps_b = 0.01, mom = 0.9, wd = 0.0005):
    num_layers = model.num_layers
    num_weights = model.num_weights
    last = time.time()
    minibatch_size = minibatch_size # / num_gpu
    for i in xrange(num_epochs):
        print "---------------------Epoch #", i
        weightsgrad = [[None] * num_weights for z in range(num_gpu)]
        biasgrad = [[None] * num_weights for z in range(num_gpu)]
        for j in xrange(1, 1024):
            count = j % num_gpu
            owl.set_device(gpu_array[count])
            data = owl.randn([227, 227, 3, minibatch_size], 0, 1)
            label = owl.randn([1, minibatch_size], 0, 1)
            out = train_one_mb(model, data, label, weightsgrad[count], biasgrad[count], dropout_rate)
            for k in weightsgrad[count]:
                k.start_eval()
            for k in biasgrad[count]:
                k.start_eval()
            if count == 0:
                for k in range(0, num_gpu):
                    for l in weightsgrad[k]:
                        l.wait_for_eval()
                    for l in biasgrad[k]:
                        l.wait_for_eval()
                print "time: %s" % (time.time() - last)
                last = time.time()

if __name__ == '__main__':
    owl.initialize(sys.argv)
    owl.create_cpu_device()
    if num_gpu == 1:
        gpu_array.append(owl.create_gpu_device(one_gpu_id))
    else:
        for i in range(num_gpu):
            gpu_array.append(owl.create_gpu_device(i))
    owl.set_device(gpu_array[0])
    model = AlexModel()
    model.init_random()
    train_network(model)

