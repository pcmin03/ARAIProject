import cv2
import skimage
import torch, glob
import numpy as np
#import pydensecrf.densecrf as dcrf
#import pydensecrf.utils as utils

from natsort import natsorted

import torch.nn.functional as F
from torch.utils.data import  Dataset
from torch import nn
from torch import einsum
from torch.autograd import Variable
from sklearn.model_selection import KFold
from scipy import ndimage

from skimage.transform import resize
from skimage.morphology import medial_axis, skeletonize
from skimage.filters import threshold_otsu,threshold_yen , threshold_local
######################################################################

#-------------------------------RMSE---------------------------------#

######################################################################
            
class Custom_Adaptive_gausian_DistanceMap(torch.nn.Module):
    
    def __init__(self,weight,distanace_map=False,select_MAE='RMSE',treshold_value=0.35,back_filter=False):
        super(Custom_Adaptive_gausian_DistanceMap,self).__init__()
        self.weight = weight
        self.dis_map = distanace_map
        self.select_MAE = select_MAE
        self.treshold_value = treshold_value
        self.back_filter = back_filter
        self.MSE = nn.MSELoss()

    def gaussian_fn(self,predict,label,labmda,channel,select_MAE): 

        i = channel
        # = torch.abs(predict[:,i:i+1]-label[:,i:i+1])
        if select_MAE == 'SIGRMSE'or select_MAE == 'MSE':
            gau_numer = torch.pow(torch.abs(predict[:,i:i+1]-label[:,i:i+1]),2)
        elif select_MAE == 'SIGMAE' or select_MAE == 'MAE':
            gau_numer = torch.abs(predict[:,i:i+1]-label[:,i:i+1])
        
        gau_deno = 1
        ch_gausian = torch.exp(-1*torch.exp(torch.tensor(1).float().cuda())*(gau_numer))

        if channel == 0: 
            ch_one  = ((label[:,i:i+1])*(ch_gausian+0.03)).float()
            ch_zero = (1-label[:,i:i+1]).float()
        else : 
            ch_one  = ((1-label[:,i:i+1])*(ch_gausian+0.03)).float()
            ch_zero = (label[:,i:i+1]).float()

        return ch_one,ch_zero, gau_numer.float()

    def forward(self, net_output, gt,mask_inputs,distance_map,phase):
         
        # postive predict label            
        if self.back_filter == True:
            zero_img = torch.zeros_like(mask_inputs)
            one_img = torch.ones_like(mask_inputs)
            # treshold_value = threshold_yen(mask_inputs.cpu().numpy()) 
            mask_img = torch.where(mask_inputs>self.treshold_value,one_img,zero_img)
            back_gt = torch.where(mask_inputs>self.treshold_value,zero_img,one_img)
            gt[:,0:1] = back_gt
            # stack_distance_map = torch.cat((distance_map,distance_map,distance_map,distance_map))
            # print(stack_distance_map.shape)
            # gt = gt*(1+stack_distance_map)

        back_one,back_zero,BEloss = self.gaussian_fn(net_output,gt,distance_map,0,self.select_MAE)
        # body_one,body_zero,BOloss = self.gaussian_fn(net_output,gt,distance_map,1,self.select_MAE)
        dend_one,dend_zero,DEloss = self.gaussian_fn(net_output,gt,distance_map,1,self.select_MAE)
        axon_one,axon_zero,AXloss = self.gaussian_fn(net_output,gt,distance_map,2,self.select_MAE)
         
        if self.select_MAE == 'MAE' or self.select_MAE == 'MSE':
            # total_loss = torch.mean(BEloss)+torch.mean(BOloss)+torch.mean(DEloss)+torch.mean(AXloss)
            total_loss = torch.mean(BEloss+BOloss+DEloss+AXloss)
            
            return total_loss

        elif self.select_MAE == 'SIGRMSE' or  self.select_MAE == 'SIGMAE':
            
            # ADBEloss = (back_one + back_zero) * BEloss
            # ADBOloss = (body_one + body_zero) * BOloss
            ADDEloss = (dend_one + dend_zero) * DEloss
            ADAXloss = (axon_one + axon_zero) * AXloss
            # torch.mean(BEloss) +
            total_loss = torch.mean(BEloss) + torch.mean(ADDEloss) + torch.mean(ADAXloss)
            # total_loss = torch.mean(BEloss+BOloss+ADDEloss+ADAXloss)
            
            return total_loss/3

        # BEMAE,BOMAE,DEMAE,AXMAE = MAE[:,0:1],MAE[:,1:2],MAE[:,2:3],MAE[:,3:4]
        # BEMSE,BOMSE,DEMSE,AXMSE = MSE[:,0:1],MSE[:,1:2],MSE[:,2:3],MSE[:,3:4]

        # BEMAE = torch.abs(net_output[:,0:1] - gt[:,0:1])
        # BOMAE = torch.abs(net_output[:,1:2] - gt[:,1:2])
        # DEMAE = torch.abs(net_output[:,2:3] - gt[:,2:3])
        # AXMAE = torch.abs(net_output[:,3:4] - gt[:,3:4])
        
        # BEMSE = torch.pow(BEMAE,2)
        # BOMSE = torch.pow(BOMAE,2)
        # DEMSE = torch.pow(DEMAE,2)
        # AXMSE = torch.pow(AXMAE,2)
        
        # MAE = torch.abs(net_output - gt) #L1 loss
        # MSE = torch.mul(MAE,MAE).float()
######################################################################

#-----------------------------TV loss--------------------------------#

######################################################################
class TVLoss(nn.Module):
    def __init__(self,TVLoss_weight=1):
        super(TVLoss,self).__init__()
        self.TVLoss_weight = TVLoss_weight

    def forward(self,x):
        batch_size = x.size()[0]
        h_x = x.size()[2]
        w_x = x.size()[3]
        count_h = self._tensor_size(x[:,:,1:,:])
        count_w = self._tensor_size(x[:,:,:,1:])
        h_tv = torch.pow((x[:,:,1:,:]-x[:,:,:h_x-1,:]),2).sum()
        w_tv = torch.pow((x[:,:,:,1:]-x[:,:,:,:w_x-1]),2).sum()
        return self.TVLoss_weight*2*(h_tv/count_h+w_tv/count_w)/batch_size

    def _tensor_size(self,t):
        return t.size()[1]*t.size()[2]*t.size()[3]


######################################################################

#---------------------------Recon loss-------------------------------#

######################################################################

class Custom_RMSE_regularize(torch.nn.Module):
    def __init__(self,weight,distanace_map=False,treshold_value=0.2,
            select_MAE='RMSE',partial=False):
        super(Custom_RMSE_regularize,self).__init__()
        self.weight = weight
        self.dis_map = distanace_map
        self.treshold_value = treshold_value
        self.select_MAE = select_MAE
        self.partial = partial 
        
    def make_mRMSE(self,feature):
        Bimg = feature[:,1:2]
        Dimg = feature[:,2:3]
        Cimg = feature[:,3:4]

        return torch.abs((1-feature[:,0:1]) - (Bimg + Dimg + Cimg))

    def forward(self,feature_output,mask_inputs,labels,activation='softmax'):
 
        #make mask image 

        zero_img = torch.zeros_like(mask_inputs)
        one_img = torch.ones_like(mask_inputs)
        mask_img = torch.where(mask_inputs>self.treshold_value,one_img,zero_img)
        back_mask_img = torch.where(mask_inputs>self.treshold_value,zero_img,one_img)

        # L1 loss
        if self.partial == True:

            body_part = (1-labels[:,0:1]) - (1-((1-feature_output[:,2:3]) * (1-feature_output[:,3:4] )))
            dend_part = (1-labels[:,0:1]) - (1-((1-feature_output[:,1:2]) * (1-feature_output[:,3:4] )))
            axon_part = (1-labels[:,0:1]) - (1-((1-feature_output[:,1:2]) * (1-feature_output[:,2:3] )))
 
            # sum_output = (feature_output[:,0:1] + feature_output[:,2:3])
            # sum_output = torch.ones_like(sum_output) - torch.clamp(sum_output,0,1) 

            # back_output = (1-feature_output[:,1:2])*(1-feature_output[:,3:4])
            
            sum_output = dend_part
            back_output = axon_part 
            BOMAE = torch.abs(body_part - feature_output[:,1:2])
            DEMAE = torch.abs(dend_part - feature_output[:,2:3])
            AXMAE = torch.abs(axon_part - feature_output[:,3:4])

            MAE = DEMAE + AXMAE
            
            if self.select_MAE == 'MAE':
                return [torch.mean(MAE).float() * float(self.weight),sum_output,back_output]
            elif self.select_MAE == 'RMSE':
            
                BOMSE = torch.mul(BOMAE,BOMAE)
                DEMSE = torch.mul(DEMAE,DEMAE)
                AXMSE = torch.mul(AXMAE,AXMAE)

                # sum_output  = dend_part
                
                MSE = torch.mean(DEMSE + AXMSE).float()
            
                return [MSE.float() * float(self.weight),sum_output,back_output]
        else : 
            sum_output = self.make_mRMSE(feature_output)
            
        if self.select_MAE == 'MAE':
            return [torch.mean(sum_output).float() * float(self.weight),feature_output[:,2:3],feature_output[:,3:4]]
        elif self.select_MAE == 'RMSE':
            return [torch.mean(torch.pow(sum_output,2)).float() * float(self.weight),feature_output[:,2:3],feature_output[:,3:4]]

######################################################################

#--------------------------NCdice loss-------------------------------#

######################################################################

class NCDICEloss(torch.nn.Module):
    
    def __init__(self,r=1.5):
        super(NCDICEloss,self).__init__()
        self.r = r
        self.treshold_value = 0.3
    # def dice
    # def dice_coef(self,y_true, y_pred):
    #     y_true_f = y_true.contiguous().view(y_true.shape[0], -1)
    #     y_pred_f = y_pred.contiguous().view(y_pred.shape[0], -1)
    #     intersection = torch.sum(torch.pow(torch.abs(y_true_f - y_pred_f),self.r),dim=1)
    #     # print(y_pred_f.shape,y_true_f.shape)
    #     return intersection/(torch.sum(y_true_f.pow(2),dim=1) + torch.sum(y_pred_f.pow(2),dim=1) + 1e-5)

    def forward(self, feature_output,labels,mask_inputs):
        zero_img = torch.zeros_like(mask_inputs)
        one_img = torch.ones_like(mask_inputs)
        mask_img = torch.where(mask_inputs>self.treshold_value,one_img,zero_img)
        back_gt = torch.where(mask_inputs>self.treshold_value,zero_img,one_img)

        labels[:,0:1] = back_gt

        dice = BinaryDiceLoss()
        total_loss= 0
        for i in [0,1,2,3]:
            # if i != self.ignore_index:
            dice_loss = dice( feature_output[:, i],labels[:, i])
            total_loss += dice_loss
        # print(result)
        return total_loss/labels.shape[1]

class BinaryDiceLoss(nn.Module):
    def __init__(self, smooth=1e-5, p=1.5, reduction='mean'):
        super(BinaryDiceLoss, self).__init__()
        self.smooth = smooth
        self.p = p
        self.reduction = reduction

    def forward(self, predict, target):
        assert predict.shape[0] == target.shape[0], "predict & target batch size don't match"
        predict = predict.contiguous().view(predict.shape[0], -1)
        target = target.contiguous().view(target.shape[0], -1)

        num = torch.sum(torch.pow(torch.abs(predict - target),1.5), dim=1)
        den = torch.sum(predict.pow(self.p), dim=1) + torch.sum(target.pow(self.p), dim=1) + self.smooth

        loss = num / den

        if self.reduction == 'mean':
            return loss.mean()
        elif self.reduction == 'sum':
            return loss.sum()
        elif self.reduction == 'none':
            return loss
        else:
            raise Exception('Unexpected reduction {}'.format(self.reduction))

