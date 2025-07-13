import sys
sys.path.append('./external/coco/PythonAPI')
sys.path.append('./external/refer')
import os
import argparse
import numpy as np
import json
import skimage.transform

from utils import load_vocab_dict_from_file, preprocess_sentence
from refer import REFER
from pycocotools import mask as cocomask


def build_coco_batches(output_dir, dataset, setname, T, input_H, input_W):
    im_dir = './data/coco/'
    im_type = 'train2014'
    vocab_file = './data/vocabulary_Gref.txt'

    data_folder = output_dir + '/' + dataset + '/' + setname + '_batch/'
    data_prefix = dataset + '_' + setname
    if not os.path.isdir(data_folder):
        os.makedirs(data_folder)

    if dataset == 'Gref':
        refer = REFER('./external/refer/data', dataset = 'refcocog', splitBy = 'google')
    elif dataset == 'unc':
        refer = REFER('./external/refer/data', dataset = 'refcoco', splitBy = 'unc')
    elif dataset == 'unc+':
        refer = REFER('./external/refer/data', dataset = 'refcoco+', splitBy = 'unc')
    else:
        raise ValueError('Unknown dataset %s' % dataset)
    refs = [refer.Refs[ref_id] for ref_id in refer.Refs if refer.Refs[ref_id]['split'] == setname]
    vocab_dict = load_vocab_dict_from_file(vocab_file)

    n_batch = 0
    for ref in refs:
        ref_id = ref['ref_id']
        image_id = ref['image_id']
        ann_id = ref['ann_id']

        im_name = 'COCO_' + im_type + '_' + str(image_id).zfill(12)
        im = skimage.io.imread('%s/%s/%s.jpg' % (im_dir, im_type, im_name))
        seg = refer.Anns[ann_id]['segmentation']
        rle = cocomask.frPyObjects(seg, im.shape[0], im.shape[1])
        mask = np.max(cocomask.decode(rle), axis = 2).astype(np.float32)

        # skimage.transform.resize(im, [resized_h, resized_w])
        if 'train' in setname:
            # im = skimage.img_as_ubyte(im_processing.resize_and_pad(im, input_H, input_W))
            # mask = im_processing.resize_and_pad(mask, input_H, input_W)
            im_h, im_w = im.shape[:2]
            scale = min(input_H / im_h, input_W / im_w)
            resized_h = int(np.round(im_h * scale))
            resized_w = int(np.round(im_w * scale))
            im = skimage.img_as_ubyte(skimage.transform.resize(im, [resized_h, resized_w]))
            mask = skimage.transform.resize(mask, [resized_h, resized_w])
        if im.ndim == 2:
            im = np.tile(im[:, :, np.newaxis], (1, 1, 3))
    
        # Get all referring objects from the same image, excluding current one
        other_refs_same_image = [
            r for r in refer.imgToRefs[image_id]
            if r != ref_id
        ]

        for sentence in ref['sentences']:
            print('saving batch %d' % (n_batch + 1))
            sent = sentence['sent']
            text = preprocess_sentence(sent, vocab_dict, T)

            negative_sents = []
            for neg_ref_id in other_refs_same_image:
                neg_ref = refer.Refs[neg_ref_id]
                neg_sentences = neg_ref['sentences']
                if len(neg_sentences) > 0:
                    for neg_sentence in neg_sentences:
                        neg_sent = neg_sentence['sent']
                        negative_sents.append(neg_sent)
            # Pad or truncate to fixed number of negatives (e.g., 3)
            max_neg = 3 # TODO: change this to 1+K (K as a parameter)
            if len(negative_sents) > 0:
                # random select max_neg negatives from negative_sents, store in neg_sent_batch
                neg_sent_batch = []
                while len(neg_sent_batch) < max_neg:
                    neg_sent_batch.append(negative_sents[np.random.randint(0, len(negative_sents))])
            else: # sample randomly from all sentences (from other images)
                neg_sent_batch = []
                while len(neg_sent_batch) < max_neg:
                    neg_ref = refer.Refs[np.random.choice(list(refer.Refs.keys()))]
                    neg_sentence = neg_ref['sentences'][np.random.randint(0, len(neg_ref['sentences']))]
                    neg_sent = neg_sentence['sent']
                    neg_sent_batch.append(neg_sent)
                
            # Stack into a single array
            neg_text_batch = [preprocess_sentence(neg_sent, vocab_dict, T) for neg_sent in neg_sent_batch]
            neg_sent_batch = np.stack(neg_sent_batch, axis=0)
            neg_text_batch = np.stack(neg_text_batch, axis=0)

            np.savez(file = data_folder + data_prefix + '_' + str(n_batch) + '.npz',
                text_batch = text,
                im_batch = im,
                mask_batch = (mask > 0),
                sent_batch = [sent],
                im_name_batch = im_name,
                neg_sent_batch = neg_sent_batch,
                neg_text_batch = neg_text_batch
            )
            n_batch += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', type = str, default = 'unc') # 'unc', 'unc+', 'Gref'
    parser.add_argument('-t', type = str, default = 'train') # 'test', val', 'testA', 'testB'
    parser.add_argument('--img-size', type = int, default = 480)
    parser.add_argument('--output-dir', type = str, default ='data/refcoco/')

    args = parser.parse_args()
    T = 20
    input_H = args.img_size
    input_W = args.img_size
    build_coco_batches(args.output_dir, dataset = args.d, setname = args.t,
            T = T, input_H = input_H, input_W = input_W)