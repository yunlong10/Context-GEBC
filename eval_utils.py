from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import torch
import numpy as np
import json
from collections import OrderedDict
from tqdm import tqdm


from densevid_eval3.eval_soda import eval_soda
from densevid_eval3.eval_para import eval_para
from densevid_eval3.eval_dvc import eval_dvc

from misc.plot_proposal_distribution import main as plot_proposal_distribution

def calculate_avg_proposal_num(json_path):
    data = json.load(open(json_path))
    return np.array([len(v) for v in data['results'].values()]).mean()

def convert_tapjson_to_dvcjson(tap_json, dvc_json):
    data = json.load(open(tap_json, 'r'))
    data['version'] = "VERSION 1.0"
    data['external_data'] = {'used:': True, 'details': "C3D pretrained on Sports-1M"}

    all_names = list(data['results'].keys())
    for video_name in all_names:
        for p_info in data['results'][video_name]:
            p_info['timestamp'] = p_info.pop('segment')
            p_info['proposal_score'] = p_info.pop('score')
            p_info['sentence_score'] = p_info.pop('sentence_score', 0)
        data['results']["v_" + video_name] = data['results'].pop(video_name)
    json.dump(data, open(dvc_json, 'w'))


def convert_dvcjson_to_tapjson(dvc_json, tap_json):
    data = json.load(open(dvc_json, 'r'))['results']
    out = {}
    out['version'] = "VERSION 1.0"
    out['external_data'] = {'used:': True, 'details': "GT proposals"}
    out['results'] = {}

    all_names = list(data.keys())
    for video_name in all_names:
        video_info = []
        event_num = len(data[video_name])
        timestamps = [data[video_name][i]['timestamp'] for i in range(event_num)]
        sentences = [data[video_name][i]['sentence'] for i in range(event_num)]
        for i, timestamp in enumerate(timestamps):
            score = data[video_name][i].get('proposal_score', 1.0)
            video_info.append({'segment': timestamp, 'score': score, 'sentence': sentences[i], 'sentence_score': data[video_name][i].get('sentence_score', 0)})
        out['results'][video_name[2:]] = video_info
    json.dump(out, open(tap_json, 'w'))


def convert_gtjson_to_tapjson(gt_json, tap_json):
    data = json.load(open(gt_json, 'r'))
    out = {}
    out['version'] = "VERSION 1.0"
    out['external_data'] = {'used:': True, 'details': "GT proposals"}
    out['results'] = {}

    all_names = list(data.keys())
    for video_name in all_names:
        video_info = []
        timestamps = data[video_name]['timestamps']
        sentences = data[video_name]['sentences']
        for i, timestamp in enumerate(timestamps):
            video_info.append({'segment': timestamp, 'score': 1., 'sentence': sentences[i]})
        out['results'][video_name[2:]] = video_info
    with open(tap_json, 'w') as f:
        json.dump(out, f)

def convert_tapjson_to_gtjson(dvc_json, out_json, reference_json='data/anet/captiondata/val_1.json'):
    fake_sent = 'None None'
    gt_data = json.load(open(reference_json, 'r'))
    data = json.load(open(dvc_json, 'r'))['results']
    out = {}
    for vid, vid_info in data.items():
        out['v_'+vid] = {'timestamps':[], 'sentences':[]}
        vid_info = sorted(vid_info, key=lambda x: x['segment'][0])
        for p in vid_info:
            out['v_'+vid]['timestamps'].append(p['segment'])
            out['v_'+vid]['sentences'].append(fake_sent)
            out['v_'+vid]['duration'] = gt_data['v_' + vid]['duration']
    with open(out_json, 'w') as f:
        json.dump(out, f)
    

def get_topn_from_dvcjson(dvc_json, out_json, top_n=3, ranking_key='proposal_score', score_thres=-1e8):
    data = json.load(open(dvc_json, 'r'))['results']
    out = {}
    out['version'] = "VERSION 1.0"
    out['external_data'] = {'used:': True, 'details': "GT proposals"}
    out['results'] = {}
    all_names = list(data.keys())
    num = 0
    bad_vid = 0
    for video_name in all_names:
        info = data[video_name]
        new_info = sorted(info, key=lambda x: x[ranking_key], reverse=True)
        new_info = [p for p in new_info if p[ranking_key] > score_thres]
        new_info = new_info[:top_n]
        out['results'][video_name] = new_info
        num += len(new_info)
        if len(new_info) == 0:
            bad_vid += 1
            out['results'].pop(video_name)
    print('average proosal number: {}'.format(num / len(all_names)))
    print('bad videos number: {}'.format(bad_vid))
    print('good videos number: {}'.format(len(out['results'])))
    with open(out_json, 'w') as f:
        json.dump(out, f)

def eval_metrics(dvc_filename, gt_filenames, para_gt_filenames, dvc_eval_version='2018', verbose=False):
    score = collections.defaultdict(lambda: -1)

    # top_n = 3
    # top_n_filename = dvc_filename + '.top{}.json'.format(top_n)
    # get_topn_from_dvcjson(dvc_filename, top_n_filename, top_n=top_n, ranking_key=ranking_key)
    # dvc_score = eval_dvc(json_path=top_n_filename, reference=gt_filenames)
    # dvc_score = {k: sum(v) / len(v) for k, v in dvc_score.items()}
    # dvc_score.update(eval_soda(top_n_filename, ref_list=gt_filenames))
    # dvc_score.update(eval_para(top_n_filename, referneces=para_gt_filenames))
    # for key in dvc_score.keys():
    #     score[key] = dvc_score[key]
    dvc_score = eval_dvc(json_path=dvc_filename, reference=gt_filenames, version=dvc_eval_version, verbose=verbose)
    dvc_score = {k: sum(v) / len(v) for k, v in dvc_score.items()}
    dvc_score.update(eval_soda(dvc_filename, ref_list=gt_filenames))
    #dvc_score.update(eval_para(dvc_filename, referneces=para_gt_filenames))
    dvc_score.update({'MetaScore': dvc_score['CIDEr'] + dvc_score['ROUGE_L'] + dvc_score['SPICE']})
    score.update(dvc_score)
    return score


def save_dvc_json(out_json, path, verbose=False):
    with open(path, 'w') as f:
        if verbose:
            out_json['valid_video_num'] = len(out_json['results'])
            out_json['avg_proposal_num'] = np.array([len(v) for v in out_json['results'].values()]).mean().item()
        json.dump(out_json, f)

def reranking(p_src, alpha, cl_score_weight, temperature):
    print('alpha: {}, temp: {}'.format(alpha, temperature))
    d = json.load(open(p_src))
    d_items = list(d['results'].items())
    for k,v in d_items:
        if True:
            sent_scores = [p['sentence_score'] / (float(len(p['sentence'].split()))**(temperature) + 1e-5) for p in v]
            prop_score = [p['proposal_score'] for p in v]
            cl_score = [p['cl_score'] for p in v]
            joint_score = alpha * (np.array(sent_scores)) + (np.array(prop_score)) + cl_score_weight * np.array(cl_score)
        for i,p in enumerate(v):
            p['joint_score'] = joint_score[i]
        v = sorted(v, key=lambda x: x['joint_score'], reverse=True)
        topN = v[0]['pred_event_count']
        v = v[:topN]
        v = sorted(v, key=lambda x: x['timestamp'])
        d['results'][k] = v
    save_path = p_src+'_rerank_alpha{}_temp{}.json'.format(alpha, temperature)
    save_dvc_json(d, save_path)
    return save_path

def selecting(p_src, selector_indices):
    d = json.load(open(p_src))
    d_items = list(d['results'].items())
    for k,v in d_items:
        indices = selector_indices[k]
        d['results'][k] = [v[pid] for pid in indices]
    save_path = p_src+'_selector.json'
    save_dvc_json(d, save_path)
    return save_path

def evaluate(model, criterion, contrastive_criterion, postprocessors, loader, dvc_json_path, logger=None, score_threshold=0,
             alpha=0.3, dvc_eval_version='2018', device='cuda', debug=False, skip_lang_eval=False, verbose=False, tokenizer=None, disable_selector=False):
    out_json = {'results': {},
                'version': "VERSION 1.0",
                'external_data': {'used:': True, 'details': None}}

    opt = loader.dataset.opt
    enable_ranking_by_logit = True if disable_selector or not opt.enable_selector else False

    select_indices_json = {}
    loss_sum = OrderedDict()
    with torch.set_grad_enabled(False):
        for dt in tqdm(loader, disable=opt.disable_tqdm):
            dt = {key: _.to(device) if isinstance(_, torch.Tensor) else _ for key, _ in dt.items()}
            dt = collections.defaultdict(lambda: None, dt)

            dt['video_target'] = [
                    {key: _.to(device) if isinstance(_, torch.Tensor) else _ for key, _ in vid_info.items()} for vid_info in
                    dt['video_target']]

            captions = list()
            for video_sents in dt['cap_raw']:
                captions.extend(video_sents)

            if opt.enable_contrastive:
                text_encoder_input = tokenizer(captions, return_tensors='pt', truncation=True, padding=True, max_length=opt.max_text_input_len)
                text_encoder_input = {key: _.to(opt.device) if isinstance(_, torch.Tensor) else _ for key, _ in text_encoder_input.items()}
                dt['text_encoder_input'] = text_encoder_input
            output, loss = model(dt, criterion, contrastive_criterion, opt.transformer_input_type, eval_mode=True)
            orig_target_sizes = dt['video_length'][:, 1]

            weight_dict = criterion.weight_dict
            final_loss = sum(loss[k] * weight_dict[k] for k in loss.keys() if k in weight_dict)

            for loss_k, loss_v in loss.items():
                loss_sum[loss_k] = loss_sum.get(loss_k, 0) + loss_v.item()
            loss_sum['total_loss'] = loss_sum.get('total_loss', 0) + final_loss.item()

            results = postprocessors['bbox'](output, orig_target_sizes, loader, model, tokenizer, enable_ranking_by_logit=enable_ranking_by_logit)


            batch_json = {}
            for idx, video_name in enumerate(dt['video_key']):
                segment = results[idx]['boxes'].cpu().numpy()
                is_gt_proposals = opt.transformer_input_type == 'gt_proposals'
                segment_num = len(segment)
                raw_boxes = results[idx]['raw_boxes'].cpu().numpy()
                raw_boxes_mask = raw_boxes.sum(1) != 0
                # pdb.set_trace()
                batch_json[video_name] = [
                    {
                        "timestamp": segment[pid].tolist(),
                        "raw_box": raw_boxes[pid].tolist(),
                        "label": results[idx]['labels'][pid].item(),
                        "proposal_score": results[idx]['scores'][pid].item(),
                        "sentence": results[idx]['captions'][pid],
                        "sentence_score": results[idx]['caption_scores'][pid],
                        "cl_score": results[idx]['cl_scores'][pid],
                        'query_id': results[idx]['query_id'][pid].item(),
                        'vid_duration': results[idx]['vid_duration'].item(),
                        'pred_event_count': results[idx]['pred_seq_len'].item(),
                    }
                    for pid in range(segment_num) if results[idx]['scores'][pid].item() > score_threshold and raw_boxes_mask[pid]]
                
            out_json['results'].update(batch_json)
            if debug and len(out_json['results']) > 5:
                break  
    save_dvc_json(out_json, dvc_json_path, verbose=True)

    for k in loss_sum.keys():
        loss_sum[k] = np.round(loss_sum[k] / (len(loader) + 1e-5), 3).item()
    logger.info('loss: {}'.format(loss_sum))


    if opt.count_loss_coef > 0 and enable_ranking_by_logit:
        dvc_json_path = reranking(dvc_json_path, alpha=alpha, cl_score_weight=opt.eval_matching_score_weight, temperature=2.0)
    elif not enable_ranking_by_logit:
        dvc_json_path = selecting(dvc_json_path, select_indices_json)

    scores = eval_metrics(dvc_json_path,
                            gt_filenames=opt.gt_file_for_eval,
                            para_gt_filenames=opt.gt_file_for_para_eval,
                            dvc_eval_version=dvc_eval_version,
                            verbose=verbose
                            )
    return scores, loss_sum

def collect_tal_result(out, name_map):
    tal_out = {'results':{}, 'version':'VERSION 1.3', 'external_data':{}}
    for key, items in out['results'].items():
        key = key[2:]
        tal_items = []
        for pred in items:
            label = pred['label']
            segment = pred['timestamp']
            score = pred['proposal_score']
            tal_item = {
                'label':name_map.convert_idx2name(label),
                'segment':segment,
                'score':score
            }
            tal_items.append(tal_item)
        tal_out['results'].update({key: tal_items})
    return tal_out

