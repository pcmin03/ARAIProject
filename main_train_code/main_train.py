import numpy as np
import skimage 
import os ,tqdm, glob , random
import torch
import torch.nn.functional as F
import yaml

from torch import nn, optim
from torchvision import models ,transforms
from torch.utils.data import DataLoader, Dataset
from torch.autograd import Variable

#custom set#
from my_network import *
from neuron_util import *
from neuron_util import channel_wise_segmentation
from my_loss import *
import config
from mydataset import prjection_mydataset,mydataset_2d
from logger import Logger
from metrics import *
import argparse

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--knum', help='Select Dataset')
parser.add_argument('--gpu', help='comma separated list of GPU(s) to use.')
parser.add_argument('--weight_decay',help='set weight_decay',type=float)
args = parser.parse_args()


with open('my_config.yml') as f:
    conf = yaml.load(f)

batch_size = 110
num_workers = 8
learning_rate = 1e-4
end_rate = 1e-6
paralle = False
use_scheduler = 'Cosine'
cross_validation = True
epochs = 2000
best_epoch = 0
best_axon = 0
best_dend = 0
betavalue = 2
F1best = 0
eval_channel = 4
knum = args.knum
print(knum,'=============')
foldnum = 10
classnum = 8
phase = 'train'
model = 'unet'
# ../unetmodel9Adaptive_weight_decay__0.001/
# name = 'Adaptive_loss_weight_decay'
# name = 'Adaptive_weight_decay_sample'
# name = 'CE_DICE'

# name = 'Dice_ignore_index_axon'
# name = 'MT_L1_loss'
# name = 'Adaptive_loss_refine_weight'
# name = 'Adaptive_weight_decay_multiTask'
name = 'Adaptive_weight_decay_v2_MUltitask'
# name = 'Adaptive_weight_decay__'
# name = 'Axon_Adpative_loss'
# name = 'CE_ignore_index_dend'
# unetmodel2Adaptive_loss_weight_decay0.001
# os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
changestep = 20
worst = 10
weight = args.weight_decay
# path = '../nested_CV_nest_net_loss'+str(knum)+'/'
path = '../'+str(model)+'model'+str(knum)+str(name)+str(weight)+'/'
if model=='res_unet':
    batch_size = 25
if model == 'efficnet_unet':
    batch_size = 30
# path = '../'+str(model)+'model'+str(knum)+str(name)+str(weight)+'/'

# path  = '../res_unet_loss_single_nested_CV_unet'+str(knum)+'/'
# path = '../nest_unetnew_model3/'
# path = '../nest_unetmodel4/'
# path = '../res_unetmode'

# path = '../nested_CV_nest_net_loss'+str(knum)+'/'

# path = '../pre_result_unet_loss_single2_summary_model_crf/'
# path = '../res_unetfull_model3_new/'
# path = '../pre_result_unet_loss_single2_summary_model_NestedUNet/'

# path ='../nest_unetfull_model3_new/'
deepsupervision = True
trainning = True
testing = True
use_postprocessing = True
deleteall = False
load_pretrain = False
patchwise = False
multi = False
multi_ = False
#set data path 
imageDir= '../project_original_image/'
labelDir = '../project_label_image/'
testDir ='../3d_data/3d_data_orginal_test2/'
tlabelDir = '../3d_data/3d_data_test_label2/'

# if model == 'res_unet':
#     batch_size = 5
   

# if cross_validation == False:
#     # Dataloader
#     MyDataset = {'train': DataLoader(prjection_mydataset(imageDir,labelDir,True,cross_validation),
#                                     batch_size, 
#                                     shuffle = True,
#                                     num_workers = num_workers),
#                 'test' : DataLoader(prjection_mydataset(testDir,tlabelDir,False,cross_validation),
#                                     1, 
#                                     shuffle = True,
#                                     num_workers = num_workers)}

#set devices
device = torch.device('cuda:'+str(args.gpu)if torch.cuda.is_available() else "else")

#set paralle
if model == 'unet':
    gen = pretrain_unet(classnum).to(device)
elif model =='nest_unet':
    gen = NestedUNet(input_channels=1,deepsupervision=deepsupervision).to(device)
elif model =='res_unet':
    gen = Segmentataion_resnet101unet().to(device)
elif model == 'efficent_unet':
    gen = pretrain_efficent_unet().to(device)
elif model == 'Multi_UNet':
    gen = Multi_UNet().to(device)

if paralle == True:
    gen = torch.nn.DataParallel(gen, device_ids=[0,1])



optimizerG = optim.Adam(gen.parameters(),lr=learning_rate)

if use_scheduler == 'Cosine':
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(optimizerG,100,T_mult=1,eta_min=end_rate)

if deleteall==True:
    logger = Logger(path,batch_size=batch_size,delete=deleteall,num=str(knum),name=model+name)

else:
    logger = Logger(path,batch_size=batch_size,delete=False,num=str(knum),name=model+name)
    #training
    
if load_pretrain == True:
    # if os.path.exists(path+"lastsave_models{}.pth"):
    checkpoint = torch.load(path +"lastsave_models{}.pth")
    gen.load_state_dict(checkpoint['gen_model'])


#set loss
# criterion = Custom_WeightedCrossEntropyLossV2().to(device)

# criterion = Custom_Adaptive().to(device)
# criterion = Custom_CE().to(device)
# criterion = Custom_CE().to(device)
# criterion = BinaryDiceLoss().to(device)
# criterion = Custom_Adaptive_RMSE().to(device)
# criterion = DiceLoss(ignore_index=1).to(device)
# criterion = Custom_Adaptive().to(device)
criterion = Custom_Adaptive_DistanceMap().to(device)
# criterion = Custom_WeightedCrossEntropyLossV2().to(device)
# criterion = nn.BCELoss().to(device)
# criterion = nn.BCELoss().to(device)
# criterion = nn.BCELoss().to(device)

# criterion = nn.CrossEntropyLoss().to(device)
# criterion = Custom_Adaptive_DistanceMap().to(device)
#set matrix score
evaluator = Evaluator(eval_channel)
inversevaluator = Evaluator(eval_channel)

vevaluator = Evaluator(eval_channel)
inversvevaluator = Evaluator(eval_channel)



image,labels = divide_kfold(imageDir,labelDir,k=foldnum,name='test')
train_num, test_num = 'train'+str(knum), 'test'+str(knum)
image_valid = image[train_num][-3:]
label_valid = labels[train_num][-3:]
image_train = image[train_num][:-3]
label_train = labels[train_num][:-3]
if trainning == True:

    if cross_validation == True:
        print(f"{image_valid},{label_valid}")
        print(f"{image[train_num]},{labels[train_num]}")
        MyDataset = {'train': DataLoader(mydataset_2d(image_train,label_train,patchwise=patchwise,multi=multi),
                                        batch_size, 
                                        shuffle = True,
                                        num_workers = num_workers),
                    'valid' : DataLoader(mydataset_2d(image_valid,label_valid,False,patchwise=patchwise,phase='valid',multi=multi),
                                        1, 
                                        shuffle = True,
                                        num_workers = num_workers)}

    print("start trainning!!!!")
    for epoch in range(epochs):
        
        if epoch %changestep == 0:
            phase = 'valid'
            gen.eval()            
            vevaluator.reset()
            inversvevaluator.reset()
            total_IOU = []
            total_F1 = []
            total_Fbeta = []
            total_recall = []
            total_predict = []

            inversetotal_IOU = []
            inversetotal_F1 = []
            inversetotal_Fbeta = []
            inversetotal_recall = []
            inversetotal_predict = []
        else : 
            phase = 'train'
            gen.train()  
            evaluator.reset()
            inversevaluator.reset()
        print(f"{epoch}/{epochs}epochs,IR=>{get_lr(optimizerG)},best_epoch=>{best_epoch},phase=>{phase}")
        print(f"==>{path}<==")
        for i, batch in enumerate(MyDataset[phase]):
            
            _input, _label = Variable(batch[0]).to(device), Variable(batch[1]).to(device)
            
            if phase == 'train':
                optimizerG.zero_grad()
                torch.autograd.set_detect_anomaly(True)

                if deepsupervision==True and model == 'nest_unet':   
                    loss = 0
                    predict = gen(_input)
                    for spre in predict:
                        loss += criterion(spre,_label)
                    loss /= len(predict)
                    seg_loss_body = loss
                    seg_loss_body.backward(retain_graph = True)
                    predict = spre
                elif model == 'Multi_UNet':
                    body, dend, axon = gen(_input)
                    
                    back_gt    = torch.where(_label==0,torch.ones_like(_label),torch.zeros_like(_label))
                    body_lable = torch.where(_label==1,torch.ones_like(_label),torch.zeros_like(_label))
                    dend_lable = torch.where(_label==2,torch.ones_like(_label),torch.zeros_like(_label))
                    axon_lable = torch.where(_label==3,torch.ones_like(_label),torch.zeros_like(_label))
                    # body_lable = _label[:,1]
                    # dend_lable = _label[:,2]
                    # axon_lable = _label[:,3]

                    body_loss = criterion(body, body_lable.float())
                    dend_loss = criterion(dend, dend_lable.float())
                    axon_loss = criterion(axon, axon_lable.float())
                    
                    total_loss = (body_loss + dend_loss + axon_loss)/3
                    total_loss.backward(retain_graph = True)
                    print(torch.argmax(body,dim=1).cpu().numpy(),'12312312312321')
                    seg_loss_body = total_loss
                    CE_loss = seg_loss_body
                    evaluator.add_batch(body_lable.cpu().numpy(),torch.argmax(body,dim=1).cpu().numpy())
                    IOU,body_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                    body_precision, body_recall,body_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)

                    evaluator.add_batch(dend_lable.cpu().numpy(),torch.argmax(dend,dim=1).cpu().numpy())
                    IOU,dend_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                    dend_precision, dend_recall,dend_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)

                    evaluator.add_batch(axon_lable.cpu().numpy(),torch.argmax(axon,dim=1).cpu().numpy())
                    IOU,axon_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                    axon_precision, axon_recall,axon_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)

                    Class_IOU           = np.array([body_IOU[0],body_IOU[1],dend_IOU[1],axon_IOU[1]])
                    Class_precision     = np.array([body_precision[0],body_precision[1],dend_precision[1],axon_precision[1]])
                    Class_recall        = np.array([body_recall[0],body_recall[1],dend_recall[1],axon_recall[1]])
                    Class_Fbetascore   = np.array([body_Fbetascore[0],body_Fbetascore[1],dend_Fbetascore[1],axon_Fbetascore[1]])
                    Class_F1score = Class_Fbetascore
                else :
                    predict=gen(_input)
                    if classnum == 8:
                        CE_loss2 = criterion(predict,_label,stage='backward')
                    CE_loss = criterion(predict,_label)
                    # dice_loss = criterion_v2(predict,_label)
                    
                    seg_loss_body = CE_loss + CE_loss2
                    seg_loss_body.backward(retain_graph = True)
                    optimizerG.step()
                
                    evaluator.add_batch(_label.cpu().numpy(),torch.argmax(predict[:,0:4],dim=1).cpu().numpy())
                    IOU,Class_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                    Class_precision, Class_recall,Class_F1score = evaluator.Class_F1_score()
                    _, _,Class_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)                    
                    if classnum == 8:
                        inversevaluator.add_batch(_label.cpu().numpy(),torch.argmax(predict[:,5:8],dim=1).cpu().numpy())
                        _,inverseClass_IOU,_ = inversevaluator.Mean_Intersection_over_Union()
                        inverseClass_precision, inverseClass_recall,inverseClass_F1score = inversevaluator.Class_F1_score()
                        _, _,inverseClass_Fbetascore = inversevaluator.Class_Fbeta_score(beta=betavalue)

            
            else:
                pre_IOU = 0
                pre_ACC = 0
                loss = 0

                with torch.no_grad():
                    
                    predict=gen(_input)
                    
                    if deepsupervision==True and model == 'nest_unet':
                        for spre in predict:                
                            loss += criterion(spre,_label)
                            
                            # spre
                            # vevaluator.add_batch(_label.cpu().numpy(),spre)
                            vevaluator.add_batch(_label.cpu().numpy(),torch.argmax(spre,dim=1).cpu().numpy())
                            IOU,Class_IOU,wo_back_MIoU = vevaluator.Mean_Intersection_over_Union()
                            Acc_class,Class_ACC,wo_back_ACC = vevaluator.Pixel_Accuracy_Class()
                            Class_precision, Class_recall,Class_F1score = vevaluator.Class_F1_score()
                            _, _,Class_Fbetascore = vevaluator.Class_Fbeta_score(beta=betavalue)
                        
                        if epoch %changestep ==0:
                            total_IOU.append(Class_IOU)
                            total_F1.append(Class_F1score)
                            total_Fbeta.append(Class_Fbetascore)
                            total_recall.append(Class_recall)
                            total_predict.append(Class_precision)
                        pre_IOU += Class_IOU
                        pre_ACC += Class_ACC

                        middle_IOU = Class_IOU
                        middle_ACC = Class_ACC

                        loss /= len(predict)
                        val_loss = loss
                        predict = spre
                    elif model == 'Multi_UNet':
                        body, dend, axon = gen(_input)
                    
                        back_gt = torch.where(_label==0,torch.ones_like(_label),torch.zeros_like(_label))
                        body_lable = torch.where(_label==1,torch.ones_like(_label),torch.zeros_like(_label))
                        dend_lable = torch.where(_label==2,torch.ones_like(_label),torch.zeros_like(_label))
                        axon_lable = torch.where(_label==3,torch.ones_like(_label),torch.zeros_like(_label))
                        
                        # print(torch.argmax(axon,dim=1).cpu().numpy().max(),'12312312312321')
                        body_loss = criterion(body, body_lable.float())
                        dend_loss = criterion(dend, dend_lable.float())
                        axon_loss = criterion(axon, axon_lable.float())
                        
                        
                        
                        val_loss = axon_loss + body_loss + dend_loss
                        val_CE_loss = val_loss

                        evaluator.add_batch(body_lable.cpu().numpy(),torch.argmax(body,dim=1).cpu().numpy())
                        IOU,body_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                        body_precision, body_recall,body_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)

                        evaluator.add_batch(dend_lable.cpu().numpy(),torch.argmax(dend,dim=1).cpu().numpy())
                        IOU,dend_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                        dend_precision, dend_recall,dend_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)

                        evaluator.add_batch(axon_lable.cpu().numpy(),torch.argmax(axon,dim=1).cpu().numpy())
                        IOU,axon_IOU,wo_back_MIoU = evaluator.Mean_Intersection_over_Union()
                        axon_precision, axon_recall,axon_Fbetascore = evaluator.Class_Fbeta_score(beta=betavalue)
                        Acc_class,Class_ACC,wo_back_ACC =evaluator.Pixel_Accuracy_Class()

                        Class_IOU           = np.array([body_IOU[0],body_IOU[1],dend_IOU[1],axon_IOU[1]])
                        Class_IOU           = np.array([body_IOU[0],body_IOU[1],dend_IOU[1],axon_IOU[1]])
                        Class_precision     = np.array([body_precision[0],body_precision[1],dend_precision[1],axon_precision[1]])
                        Class_recall        = np.array([body_recall[0],body_recall[1],dend_recall[1],axon_recall[1]])
                        Class_Fbetascore   = np.array([body_Fbetascore[0],body_Fbetascore[1],dend_Fbetascore[1],axon_Fbetascore[1]])
                        Class_F1score = Class_Fbetascore
                        
                        if epoch %changestep ==0:
                            total_IOU.append(Class_IOU)
                            total_F1.append(Class_F1score)
                            total_Fbeta.append(Class_Fbetascore)
                            total_recall.append(Class_recall)
                            total_predict.append(Class_precision)
                            
                        middle_IOU = Class_IOU
                        middle_ACC = Class_ACC
                        pre_IOU = Class_IOU
                        pre_ACC = Class_ACC

                    else:
                        val_CE_loss = criterion(predict,_label)
                        # val_dice_loss = criterion_v2(predict,_label)
                        
                        val_loss = val_CE_loss 
                        # vevaluator.add_batch(_label.cpu().numpy(),predict)
                        
                        vevaluator.add_batch(_label.cpu().numpy(),torch.argmax(predict[:,0:4],dim=1).cpu().numpy())
                        IOU,Class_IOU,wo_back_MIoU = vevaluator.Mean_Intersection_over_Union()
                        Acc_class,Class_ACC,wo_back_ACC = vevaluator.Pixel_Accuracy_Class()
                        Class_precision, Class_recall,Class_F1score = vevaluator.Class_F1_score()
                        _, _,Class_Fbetascore = vevaluator.Class_Fbeta_score(beta=betavalue)

                        if classnum == 8:
                            inversevaluator.add_batch(_label.cpu().numpy(),torch.argmax(predict[:,5:8],dim=1).cpu().numpy())
                            _,inverseClass_IOU,_ = inversevaluator.Mean_Intersection_over_Union()
                            inverseClass_precision, inverseClass_recall,inverseClass_F1score = inversevaluator.Class_F1_score()
                            _, _,inverseClass_Fbetascore = inversevaluator.Class_Fbeta_score(beta=betavalue)

                        pre_IOU += Class_IOU
                        pre_ACC += Class_ACC
                        if epoch %changestep ==0:
                            total_IOU.append(Class_IOU)
                            total_F1.append(Class_F1score)
                            total_Fbeta.append(Class_Fbetascore)
                            total_recall.append(Class_recall)
                            total_predict.append(Class_precision)
                            if classnum == 8:
                                inversetotal_IOU.append(inverseClass_IOU)
                                inversetotal_F1.append(inverseClass_F1score)
                                inversetotal_Fbeta.append(inverseClass_Fbetascore)
                                inversetotal_recall.append(inverseClass_recall)
                                inversetotal_predict.append(inverseClass_precision)
                        middle_IOU = Class_IOU
                        middle_ACC = Class_ACC

                    pre_IOU = [class_IOU / 9 for class_IOU in pre_IOU]
                    pre_ACC = [class_IOU / 9 for class_IOU in pre_ACC]
                
        if  phase == 'train':
            if use_scheduler == 'Cosine':
                scheduler.step(epoch)
            summary_print = {'seg_loss_body':seg_loss_body,
                            'Class_IOU':Class_IOU,
                            'precision':Class_precision, 
                            'recall':Class_recall,
                            'F1score':Class_F1score,
                            'Fbetascore':Class_Fbetascore}
            logger.print_value(summary_print,'train')
            invesesum_print = {
                            'inverseClass_IOU':inverseClass_IOU,
                            'inverseprecision':inverseClass_precision, 
                            'inverserecall':inverseClass_recall,
                            'inverseF1score':inverseClass_F1score,
                            'inverseFbetascore':inverseClass_Fbetascore}
            logger.print_value(invesesum_print,'train')

            train_loss = {  'seg_loss_body':seg_loss_body,
                            'CE_loss':CE_loss}
            logger.summary_scalars(train_loss,epoch)
            

        elif phase == 'valid': 

            test_val = {"pre_IOU":pre_IOU,"pre_ACC":pre_ACC,"Class_IOU":Class_IOU,"Class_ACC":Class_ACC,
                        "wo_back_MIoU":wo_back_MIoU,"wo_back_ACC":wo_back_ACC,
                        'precision':Class_precision, 
                        'recall':Class_recall,
                        'F1score':Class_F1score,
                        "val_loss":val_loss,
                        'Fbetascore':Class_Fbetascore}
            logger.print_value(test_val,'test')

            inversetest_val = {"inverseClass_IOU":inverseClass_IOU,
                        'inverseprecision':inverseClass_precision, 
                        'inverserecall':inverseClass_recall,
                        'inverseF1score':inverseClass_F1score,
                        'inverseFbetascore':inverseClass_Fbetascore}
            logger.print_value(inversetest_val,'inversetest')

            IOU_scalar = dict()
            precision_scalar = dict()
            recall_scalr = dict()
            F1score_scalar = dict()
            Fbetascore_scalar = dict()
            
            
            inverseIOU_scalar = dict()
            inverseprecision_scalar = dict()
            inverserecall_scalr = dict()
            inverseF1score_scalar = dict()
            inverseFbetascore_scalar = dict()

            for i in range(4):
                IOU_scalar.update({'val_IOU_'+str(i):Class_IOU[i]})
                precision_scalar.update({'val_precision_'+str(i):Class_precision[i]})
                recall_scalr.update({'val_recall_'+str(i):Class_recall[i]})
                F1score_scalar.update({'val_F1_'+str(i):Class_F1score[i]})
                Fbetascore_scalar.update({'val_Fbeta'+str(i):Class_Fbetascore[i]})
                
                inverseIOU_scalar.update({'inverseval_IOU_'+str(i):Class_IOU[i]})
                inverseprecision_scalar.update({'inverseval_precision_'+str(i):Class_precision[i]})
                inverserecall_scalr.update({'inverseval_recall_'+str(i):Class_recall[i]})
                inverseF1score_scalar.update({'inverseval_F1_'+str(i):Class_F1score[i]})
                inverseFbetascore_scalar.update({'inverseval_Fbeta'+str(i):Class_Fbetascore[i]})
                
            validation_loss = {'val_loss':val_loss,
                                'val_CE_loss':val_CE_loss}

            logger.summary_scalars(IOU_scalar,epoch,'IOU')
            logger.summary_scalars(precision_scalar,epoch,'precision')
            logger.summary_scalars(recall_scalr,epoch,'recall')
            logger.summary_scalars(F1score_scalar,epoch,'F1')
            logger.summary_scalars(Fbetascore_scalar,epoch,'Fbeta')
            logger.summary_scalars(validation_loss,epoch)
            logger.summary_scalars({'IR':get_lr(optimizerG)},epoch,'IR')

            logger.summary_scalars(inverseIOU_scalar,epoch,'inverseIOU')
            logger.summary_scalars(inverseprecision_scalar,epoch,'inverseprecision')
            logger.summary_scalars(inverserecall_scalr,epoch,'inverserecall')
            logger.summary_scalars(inverseF1score_scalar,epoch,'inverseF1')
            logger.summary_scalars(inverseFbetascore_scalar,epoch,'inverseFbeta')
            

            if  Class_recall[3] > best_axon or Class_recall[2] > best_dend :
                torch.save({"gen_model":gen.state_dict(),
                        "optimizerG":optimizerG.state_dict(),
                        "epochs":epoch},
                        path+"bestsave_models{}.pth")
                print('save!!!')
                best_axon = Class_recall[3]
                best_dend = Class_recall[2]
                F1best = Class_F1score[3]
                best_epoch = epoch

                        
            if  epoch %changestep == 0:
                torch.save({"gen_model":gen.state_dict(),
                        "optimizerG":optimizerG.state_dict(),
                        "epochs":epoch},
                        path+"lastsave_models{}.pth")
                # print(.max())
                if multi_ == True:
                    pre_body = decode_segmap(torch.argmax(body,dim=1).cpu().numpy(),name='body')
                    pre_dend = decode_segmap(torch.argmax(dend,dim=1).cpu().numpy(),name='dend')
                    pre_axon = decode_segmap(torch.argmax(axon,dim=1).cpu().numpy(),name='axon')
                    pre_body = pre_body + pre_dend +  pre_axon
                    v_la = decode_segmap(torch.argmax(_label,dim=1).cpu().detach().numpy(),name='full')
                    _input = _input.detach().cpu().numpy()
                else : 
                    pre_body=decode_segmap(torch.argmax(predict[:,0:4],dim=1).cpu().numpy())
                    v_la=decode_segmap(_label.cpu().detach().numpy().astype('uint8'),name='full')
                    _input = _input.detach().cpu().numpy()
                    inversepre_body=decode_segmap(torch.argmax(predict[:,4:8],dim=1).cpu().numpy(),name='inverse')
                    
                    save_stack_images = {'inversepre_body':inversepre_body,'pre_body':pre_body,'v_la':v_la,'_input':_input}
                # print(total_IOU)
                logger.save_csv_file(np.array(total_IOU),name='valid_total_IOU')
                logger.save_csv_file(np.array(total_F1),name='valid_total_F1')
                logger.save_csv_file(np.array(total_Fbeta),name='valid_total_Fbeta')
                logger.save_csv_file(np.array(total_recall),name='valid_total_recall')
                logger.save_csv_file(np.array(total_predict),name='valid_total_precision')

                logger.save_csv_file(np.array(inversetotal_IOU),name='inversevalid_total_IOU')
                logger.save_csv_file(np.array(inversetotal_F1),name='inversevalid_total_F1')
                logger.save_csv_file(np.array(inversetotal_Fbeta),name='inversevalid_total_Fbeta')
                logger.save_csv_file(np.array(inversetotal_recall),name='inversevalid_total_recall')
                logger.save_csv_file(np.array(inversetotal_predict),name='inversevalid_total_precision')


                logger.save_images(save_stack_images,epoch)

if testing == True:
    #testing
    print("==========testing===============")

    gen.eval()
    logger = Logger(path,batch_size=batch_size)

    logger.changedir()
    total_IOU = []
    total_F1 = []
    total_Fbeta = []
    total_recall = []
    total_predict = []

    MyDataset = {'test' : DataLoader(mydataset_2d(image[test_num],labels[test_num],False,phase='test'),
                            1, 
                            shuffle = False,
                            num_workers = num_workers)}
    for i, batch in enumerate(MyDataset['test']):
        _input, _label = batch[0].to(device), batch[1].to(device)
        with torch.no_grad():
            loss = 0
            predict = gen(_input)
            if deepsupervision==True and model == 'nest_unet':
                for spre in predict:                
                    loss += criterion(spre,_label)
                loss /= len(predict)
                predict = spre

            else:
                val_loss = criterion(predict,_label)
            print("???????????????????????????????????????????????")
            # predict = channel_segmap(predict.cpu().numpy())
            # vevaluator.add_batch(_label.cpu().numpy(),predict)
            vevaluator.add_batch(_label.cpu().numpy(),torch.argmax(predict,dim=1).cpu().numpy())
            IOU,Class_IOU,wo_back_MIoU = vevaluator.Mean_Intersection_over_Union()
            Acc_class,Class_ACC,wo_back_ACC = vevaluator.Pixel_Accuracy_Class()
            Class_precision, Class_recall,Class_F1score = vevaluator.Class_F1_score()
            _, _,Class_Fbetascore = vevaluator.Class_Fbeta_score(beta=betavalue)

            # result_crf=np.array(decode_segmap(result_crf,name='full'))
            pre_body=decode_segmap(ch_channel(predict),nc=8,name='max')
            v_la=decode_segmap(_label.cpu().detach().numpy().astype('uint8'),nc=8,name='max')
            _input = _input.detach().cpu().numpy()
            
            total_IOU.append(Class_IOU)
            total_F1.append(Class_F1score)
            total_Fbeta.append(Class_Fbetascore)
            total_recall.append(Class_recall)
            total_predict.append(Class_precision)

            save_stack_images = {'final_predict':pre_body,'final_la':v_la,
                                'FINAL_input':_input}
            save_path=logger.save_images(save_stack_images,i)

    # logger.make_full_image(imagename='final_predict')
    logger.save_csv_file(np.array(total_IOU),name='total_IOU')
    logger.save_csv_file(np.array(total_F1),name='total_F1')
    logger.save_csv_file(np.array(total_Fbeta),name='total_Fbeta')
    logger.save_csv_file(np.array(total_recall),name='valid_total_recall')
    logger.save_csv_file(np.array(total_predict),name='valid_total_precision')
    # logger.make_full_image(imagename='post_image')
            # # print(result_crf)
            # result_crf = np.transpose(result_crf,[0,2,1])
            # # print(v_input[0].shape)
            
            # skimage.io.imsave(path+"pre_body"+"_"+str(epoch)+".png",np.transpose(pre_body[num],[1,2,0]))    
            # skimage.io.imsave(path+"labe_"+"_"+str(epoch)+".png",v_la[num])
            # skimage.io.imsave(path+"img"+"_"+str(epoch)+".png",np.transpose(v_input[num].detach().cpu().numpy(),[1,2,0]))
            # skimage.io.imsave(path+"result_crf"+"_"+str(epoch)+".png",result_crf)
        

