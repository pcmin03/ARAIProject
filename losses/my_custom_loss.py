
from .Distance_loss import * 
from .information_loss import *
from .Garborloss import *

def select_loss(args): 
    lossdict = dict()
    labelname = ""
    #my loss
    if args.RECONGAU == True:
        criterion = Custom_Adaptive_gausian_DistanceMap(float(args.weight),distanace_map=args.class_weight,select_MAE=args.Aloss,
                                                        treshold_value=args.mask_trshold,back_filter=args.back_filter)
        if args.back_filter== True:
            labelname += 'back_filter_'
        labelname += 'seg_gauadaptive_'+str(args.Aloss)+'_'+str(int(args.weight))+'_'
        
    #compare loss
    elif args.RCE == True:
        criterion = noiseCE(int(args.weight),RCE=args.RCE)
        labelname += 'RCE_'

    elif args.NCE == True:
        criterion = noiseCE(int(args.weight),NCE=args.NCE)
        labelname += 'NCE_'

    elif args.BCE == True:
        criterion = noiseCE(int(args.weight),BCE=args.BCE)
        labelname += 'BCE_'

    elif args.NCDICE == True:
        criterion = NCDICEloss(r=args.NCDICEloss)
        labelname += 'NCDICE_'+str(args.NCDICEloss)+'_'

    elif args.ADCE == True:
        criterion = Custom_CE(int(args.weight),Gaussian=False,active=args.activation)
        labelname += 'seg_adaptiveCE_'    
    
    elif args.FOCAL == True:
        criterion = FocalLoss()
        labelname += 'FOCAL'

    lossdict.update({'mainloss':criterion})
    
    lossdict.update({'subloss':Custom_CE(1,Gaussian=False,active=args.activation)})
    #second loss
    if args.RECON == True:
        reconstruction_loss = Custom_RMSE_regularize(float(args.labmda),treshold_value=args.mask_trshold,select_MAE=args.Rloss,
                                                    partial = args.partial_recon)
        
        lossdict.update({'reconloss':reconstruction_loss})
        if args.partial_recon == True:
            labelname += 'part_reconloss2_'+str(args.Rloss)+'_' + str(args.labmda)+'_'
        else : 
            labelname += 'reconloss_'+str(args.Rloss)+'_' + str(args.labmda)+'_'

    #new loss        
    if args.TVLOSS == True:
        tv_loss = TVLoss(TVLoss_weight=0.001)
        labelname += 'TVLoss_'+str(0.001)+'_'
    elif args.Gaborloss == True:
        labelname += 'garbor3_'+str(args.Gloss)+'_'+str(args.labmda2)+'_'
        if use_label == True:
            labelname += 'uselabel_'    
        gabors = dont_train(Custom_Gabor_loss(device=device,weight=float(args.labmda2),use_median=use_median,use_label=use_label).to(device))
        lossdict.update({'gaborloss':gabors})
        
    return lossdict, labelname +str(args.mask_trshold)+'_'