#!/usr/bin/env python3
"""
BS Analyzer v2.2 — Python implementation
키워드 사전 외부 모듈화 (bs_keywords_v22.json)
verdict 분류 내장 (v2.1.2에서 통합)

사용법:
  python3 bs_analyzer_v22.py <input.json> [output.json] [--dict bs_keywords_v22.json]

입력: metamong 포맷 세션 배열 JSON
출력: 조건별 분석 결과 JSON + 터미널 출력
"""

import json, re, math, sys, os
from datetime import datetime
from collections import Counter

# ============================================================
# DICTIONARY LOADER
# ============================================================

def load_dictionary(dict_path=None):
    """Load keyword dictionary from JSON. Falls back to bundled default."""
    if dict_path and os.path.exists(dict_path):
        with open(dict_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Try same directory as script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(script_dir, 'bs_keywords_v22.json')
    if os.path.exists(default):
        with open(default, 'r', encoding='utf-8') as f:
            return json.load(f)
    raise FileNotFoundError("bs_keywords_v22.json not found. Provide --dict path.")


def compile_dict(d):
    """Compile regex patterns from dictionary strings."""
    compiled = {}

    # Simple keyword lists
    compiled['AGREE'] = d['agree']
    compiled['RESIST'] = d['resist']
    compiled['HEDGE'] = d['hedge']
    compiled['HALLUC_PH'] = [(item['phrase'], item['weight']) for item in d['halluc_phrases']]
    compiled['HALLUC_CTX'] = d['halluc_context']
    compiled['HALLUC_NEG'] = d['halluc_negatives']
    compiled['ELAB_KW'] = d['elaboration_keywords']
    compiled['DIR_HI'] = d['directiveness_high']
    compiled['DIR_LO'] = d['directiveness_low']
    compiled['ELEV_CTX'] = d['elevation_context']
    compiled['GEB_KW'] = d['geb_session_keywords']

    # Compiled regex: elaboration
    compiled['ELAB_RE'] = []
    for item in d['elaboration_regex']:
        compiled['ELAB_RE'].append((re.compile(item['pattern']), item['label'], item['weight']))

    # Narrativization
    compiled['BASE_SEO_RE'] = re.compile(d['narrativization_base']['pattern'])
    compiled['NARR_FILTERED'] = d['narrativization_filtered']
    compiled['NARR_WEIGHT'] = d['narrativization_base']['weight']

    # Headway signals
    compiled['HEADWAY_SIGS'] = []
    for item in d['headway_signals']:
        compiled['HEADWAY_SIGS'].append(re.compile(item['pattern']))

    # Stemmer
    compiled['KO_SUF'] = re.compile(d['stemmer']['suffixes'])
    compiled['KO_PAR'] = re.compile(d['stemmer']['particles'])
    compiled['KO_STOP'] = set(d['stemmer']['stopwords'])

    # Reverse question
    rq = d['reverse_question']
    flags = re.MULTILINE if 'm' in rq.get('flags', '') else 0
    compiled['QRE'] = re.compile(rq['pattern'], flags)

    # Thresholds
    compiled['T'] = d['thresholds']

    # Sycophancy formula weights
    compiled['SYC_RW'] = d['syc_formula']['resist_weight']
    compiled['SYC_HW'] = d['syc_formula']['hedge_weight']

    # Condition assignment
    compiled['COND'] = d['condition_assignment']
    compiled['COND_LABELS'] = d['condition_assignment']['labels']
    compiled['COND_ORDER'] = d['condition_assignment']['order']
    compiled['GPT4O_CUTOFF'] = datetime.fromisoformat(d['condition_assignment']['gpt4o_cutoff']).timestamp()

    return compiled


# ============================================================
# CORE FUNCTIONS
# ============================================================

def stem(w, C):
    s = C['KO_SUF'].sub('', w)
    s = C['KO_PAR'].sub('', s)
    return s if len(s) > 1 else w

def tokenize(t, C):
    t2 = re.sub(r'[^\w\s가-힣]', ' ', t.lower())
    return [stem(w, C) for w in t2.split() if len(w) > 1 and stem(w, C) not in C['KO_STOP'] and len(stem(w, C)) > 1]

def jaccard(a, b):
    if not a or not b: return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)

def count_hits(text, dictionary):
    tl = text.lower()
    c = 0
    for p in dictionary:
        idx = 0; pl = p.lower()
        while True:
            f = tl.find(pl, idx)
            if f == -1: break
            c += 1; idx = f + len(pl)
    return c

def calc_syc(resp, C):
    return count_hits(resp, C['AGREE']) - (count_hits(resp, C['RESIST']) * C['SYC_RW'] + count_hits(resp, C['HEDGE']) * C['SYC_HW'])

def calc_halluc(resp, C):
    t = resp.lower()
    s = 0
    for phrase, w in C['HALLUC_PH']:
        if phrase.lower() in t:
            s += w
    for ctx in C['HALLUC_CTX']:
        kw = ctx['keyword'].lower()
        idx = t.find(kw)
        if idx == -1: continue
        win = t[max(0, idx-80):min(len(t), idx+80)]
        if any(g in win for g in ctx['geb_markers']) and not any(n.lower() in win for n in C['HALLUC_NEG']):
            s += 2
    return s

def has_elevation_context(resp, match_pos, C):
    window = C['NARR_FILTERED']['window']
    start = max(0, match_pos - window)
    end = min(len(resp), match_pos + window)
    surrounding = resp[start:end].lower()
    return any(ctx.lower() in surrounding for ctx in C['ELEV_CTX'])

def calc_elab(resp, C):
    s = 0; matches = []
    for regex, label, w in C['ELAB_RE']:
        if regex.search(resp):
            s += w; matches.append(label)
    # Narrativization: base (unconditional) + filtered ("존재의" with context)
    seo_hit = False
    if C['BASE_SEO_RE'].search(resp):
        seo_hit = True
    else:
        kw = C['NARR_FILTERED']['keyword']
        for m in re.finditer(re.escape(kw), resp):
            if has_elevation_context(resp, m.start(), C):
                seo_hit = True; break
    if seo_hit:
        s += C['NARR_WEIGHT']; matches.append('서사화')
    # Keyword fallback
    if s == 0:
        kh = count_hits(resp, C['ELAB_KW'])
        if kh > 0: s += kh; matches.append('KW_hit')
    return s, matches

def elab_level(score, C):
    if score >= C['T']['elab_strong']: return 2
    if score >= C['T']['elab_weak']: return 1
    return 0

def calc_dir(prompt, C):
    t = (prompt or '').lower()
    hi = count_hits(t, C['DIR_HI'])
    lo = count_hits(t, C['DIR_LO'])
    if hi > lo: return 'high'
    if lo > hi: return 'low'
    return 'mid'

def calc_lexical(relays, C):
    win = C['T']['lexical_window']
    res = []; user_hist = []
    for i, r in enumerate(relays):
        ut = set(tokenize(r.get('user', ''), C))
        user_hist.append(ut)
        if i < 1:
            res.append({'j': 0.0, 'd': 0.0, 'ds': 0.0}); continue
        st = max(0, i - win)
        recent = set()
        for k in range(st, i): recent |= user_hist[k]
        sys_tok = set(tokenize(r.get('system', ''), C))
        j = jaccard(recent, sys_tok)
        prev_j = res[i-1]['j'] if i > 1 else j
        res.append({'j': j, 'd': j - prev_j, 'ds': 0.0})
    # Smoothed delta
    sw = C['T']['smoothing_window']
    for i in range(len(res)):
        st = max(0, i - sw // 2); en = min(len(res)-1, i + sw // 2)
        vals = [res[k]['d'] for k in range(st, en+1)]
        res[i]['ds'] = sum(vals) / len(vals)
    return res


# ============================================================
# CONDITION ASSIGNMENT
# ============================================================

def assign_condition(s, C):
    src = s.get('source', '')
    gc = s.get('gebClass', '')
    title = (s.get('title', '') or '').lower()
    g = gc == 'geb' or any(k in title for k in C['GEB_KW'])
    sd = 0
    d = s.get('date', '')
    if d and d != '?':
        try: sd = datetime.fromisoformat(d).timestamp()
        except: pass
    rules = C['COND']['rules']
    if src == 'gemini': return rules['gemini']
    elif src == 'gpt5': return rules['gpt5']
    elif src == 'gpt':
        if g: return rules['gpt_geb']
        elif sd >= C['GPT4O_CUTOFF']: return rules['gpt_post_cutoff']
        else: return rules['gpt_pre_cutoff']
    elif src == 'claude' and g: return rules['claude_geb']
    elif src == 'claude': return rules['claude_nongeb']
    return '?'


# ============================================================
# VERDICT CLASSIFICATION
# ============================================================

def classify_verdict(relays, source, cond, C):
    n = len(relays)
    if n == 0: return []
    is_claude = cond in ('C', 'D')
    T = C['T']

    ag_rates = [r['ag'] for r in relays]
    mean_ag = sum(ag_rates) / n if n > 0 else 0
    threshold = max(T['drowning_session_multiplier'] * mean_ag, T['drowning_min_agreement'])

    verdicts = []
    for i, r in enumerate(relays):
        resp = r.get('system', '') or ''
        ag = r['ag']; rs = r['rs']; hd = r['hd']
        qs = len(C['QRE'].findall(resp))

        # Stage 1: Drowning
        if ag >= threshold and rs == 0:
            conf = 'high' if ag >= threshold * T['drowning_high_conf_multiplier'] else 'medium'
            verdicts.append({'verdict': 'drowning', 'confidence': conf}); continue

        # Stage 2: Directional
        if is_claude:
            sig = sum(1 for pat in C['HEADWAY_SIGS'] if pat.search(resp))
            if sig >= T['headway_signal_high']:
                verdicts.append({'verdict': 'headway', 'confidence': 'high'})
            elif sig >= T['headway_signal_medium']:
                verdicts.append({'verdict': 'headway', 'confidence': 'medium'})
            elif rs > 0 or hd > 0:
                if len(resp) > T['flow_min_resp_len']:
                    verdicts.append({'verdict': 'headway', 'confidence': 'low'})
                else:
                    verdicts.append({'verdict': 'doldrums', 'confidence': 'low'})
            else:
                verdicts.append({'verdict': 'unclassified', 'confidence': None})
        else:
            if rs > 0 or hd > 0:
                if len(resp) > T['flow_min_resp_len']:
                    verdicts.append({'verdict': 'headway', 'confidence': 'low'})
                else:
                    verdicts.append({'verdict': 'doldrums', 'confidence': 'low'})
            elif qs > 0:
                verdicts.append({'verdict': 'headway', 'confidence': 'low'})
            else:
                verdicts.append({'verdict': 'unclassified', 'confidence': None})
    return verdicts


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze(sessions, C):
    # Per-relay metrics
    for s in sessions:
        for r in s['relays']:
            resp = r.get('system', ''); prompt = r.get('user', '')
            r['syc'] = calc_syc(resp, C)
            r['ag'] = count_hits(resp, C['AGREE'])
            r['rs'] = count_hits(resp, C['RESIST'])
            r['hd'] = count_hits(resp, C['HEDGE'])
            r['hl'] = calc_halluc(resp, C)
            el_s, el_m = calc_elab(resp, C)
            r['el'] = el_s; r['em'] = el_m
            r['dr'] = calc_dir(prompt, C)
        lx = calc_lexical(s['relays'], C)
        for i, r in enumerate(s['relays']):
            r['lj'] = lx[i]['j']; r['ld'] = lx[i]['ds']
        # Verdict
        cond = s.get('cond', '?')
        vs = classify_verdict(s['relays'], s.get('source', 'gpt'), cond, C)
        for i, r in enumerate(s['relays']):
            r['verdict'] = vs[i]['verdict'] if i < len(vs) else 'unclassified'
            r['verdict_conf'] = vs[i]['confidence'] if i < len(vs) else None

    # Aggregate by condition
    results = {}
    for ck in C['COND_ORDER']:
        ss = [s for s in sessions if s.get('cond') == ck]
        ar = [r for s in ss for r in s['relays']]
        n = len(ar)
        if n == 0: results[ck] = None; continue

        syc_scores = [r['syc'] for r in ar]
        avg_syc = sum(syc_scores) / n
        h_f = sum(1 for r in ar if r['hl'] >= C['T']['halluc_flag'])
        e_str = sum(1 for r in ar if r['el'] >= C['T']['elab_strong'])
        e_wk = sum(1 for r in ar if C['T']['elab_weak'] <= r['el'] < C['T']['elab_strong'])
        e_tot = e_str + e_wk

        lx_vals = [r['lj'] for r in ar if r['lj'] > 0]
        avg_lx = sum(lx_vals) / len(lx_vals) if lx_vals else 0

        sorted_syc = sorted(syc_scores)
        p30 = sorted_syc[int(n * C['T']['quadrant_low_pct'])]
        p70 = sorted_syc[int(n * C['T']['quadrant_high_pct'])]
        qHH = qHL = qLH = qLL = 0
        for r in ar:
            hi_s = r['syc'] >= p70; lo_s = r['syc'] <= p30; hi_e = r['el'] >= C['T']['elab_weak']
            if hi_s and hi_e: qHH += 1
            elif hi_s: qHL += 1
            elif lo_s and hi_e: qLH += 1
            else: qLL += 1

        f_lx = [r['lj'] for r in ar if r['el'] >= 1]
        u_lx = [r['lj'] for r in ar if r['el'] == 0 and r['hl'] < C['T']['halluc_flag']]
        avg_fl = sum(f_lx) / len(f_lx) if f_lx else None
        avg_ul = sum(u_lx) / len(u_lx) if u_lx else None

        d_hi = sum(1 for r in ar if r['dr'] == 'high')
        d_mid = sum(1 for r in ar if r['dr'] == 'mid')
        d_lo = sum(1 for r in ar if r['dr'] == 'low')
        ld_e = sum(1 for r in ar if r['dr'] == 'low' and r['el'] >= 1)
        hd_e = sum(1 for r in ar if r['dr'] == 'high' and r['el'] >= 1)

        avg_sys = sum(len(r.get('system', '')) for r in ar) / n
        total_chars = sum(len(r.get('system', '')) for r in ar)
        rate_1k = e_tot / (total_chars / 1000) if total_chars > 0 else 0

        # Time pattern
        min_rl = C['T']['long_session_min_relays']
        sample = C['T']['time_pattern_sample']
        e_n = l_n = e_hl = l_hl = e_el = l_el = 0; e_lx_s = l_lx_s = 0; long_s = 0
        for s in ss:
            if len(s['relays']) < min_rl: continue
            long_s += 1
            for r in s['relays'][:sample]:
                e_n += 1
                if r['hl'] >= C['T']['halluc_flag']: e_hl += 1
                if r['el'] >= 1: e_el += 1
                e_lx_s += r['lj']
            for r in s['relays'][-sample:]:
                l_n += 1
                if r['hl'] >= C['T']['halluc_flag']: l_hl += 1
                if r['el'] >= 1: l_el += 1
                l_lx_s += r['lj']

        # Verdict counts
        v_dr = sum(1 for r in ar if r.get('verdict') == 'drowning')
        v_hw = sum(1 for r in ar if r.get('verdict') == 'headway')
        v_dl = sum(1 for r in ar if r.get('verdict') == 'doldrums')
        v_uc = sum(1 for r in ar if r.get('verdict') == 'unclassified')
        v_hw_hi = sum(1 for r in ar if r.get('verdict') == 'headway' and r.get('verdict_conf') == 'high')
        v_dr_hi = sum(1 for r in ar if r.get('verdict') == 'drowning' and r.get('verdict_conf') == 'high')

        results[ck] = {
            'label': C['COND_LABELS'].get(ck, ck),
            'sessions': len(ss), 'relays': n, 'avg_sys_len': round(avg_sys),
            'avg_syc': round(avg_syc, 3),
            'halluc_flags': h_f, 'halluc_pct': round(h_f / n * 100, 2),
            'elab_strong': e_str, 'elab_weak': e_wk, 'elab_total': e_tot,
            'elab_pct': round(e_tot / n * 100, 2), 'elab_strong_pct': round(e_str / n * 100, 2),
            'avg_jaccard': round(avg_lx, 4),
            'qHH': qHH, 'qHL': qHL, 'qLH': qLH, 'qLL': qLL,
            'qLH_pct': round(qLH / n * 100, 2),
            'flagged_j': round(avg_fl, 4) if avg_fl else None,
            'unflagged_j': round(avg_ul, 4) if avg_ul else None,
            'j_diff': round(avg_fl - avg_ul, 4) if avg_fl and avg_ul else None,
            'dir_hi': d_hi, 'dir_mid': d_mid, 'dir_lo': d_lo,
            'ld_elab': ld_e, 'hd_elab': hd_e,
            'rate_1k': round(rate_1k, 4),
            'long_s': long_s, 'e_n': e_n, 'l_n': l_n,
            'e_hp': round(e_hl / e_n * 100, 2) if e_n else None,
            'l_hp': round(l_hl / l_n * 100, 2) if l_n else None,
            'e_ep': round(e_el / e_n * 100, 2) if e_n else None,
            'l_ep': round(l_el / l_n * 100, 2) if l_n else None,
            'e_lx': round(e_lx_s / e_n, 4) if e_n else None,
            'l_lx': round(l_lx_s / l_n, 4) if l_n else None,
            'v_drowning': v_dr, 'v_headway': v_hw, 'v_doldrums': v_dl, 'v_unclass': v_uc,
            'v_hw_hi': v_hw_hi, 'v_dr_hi': v_dr_hi,
        }
    return results


def sensitivity_analysis(sessions, C):
    weight_sets = [(0.3, 0.2), (0.5, 0.3), (0.7, 0.4), (1.0, 0.5)]
    sens = {}
    for rw, hw in weight_sets:
        sens[(rw, hw)] = {}
        for ck in C['COND_ORDER']:
            ar = [r for s in sessions if s.get('cond') == ck for r in s['relays']]
            n = len(ar)
            if n == 0: continue
            syc_scores = [r['ag'] - (r['rs'] * rw + r['hd'] * hw) for r in ar]
            sorted_s = sorted(syc_scores)
            p30 = sorted_s[int(n * 0.3)]
            qLH = sum(1 for i, r in enumerate(ar) if syc_scores[i] <= p30 and r['el'] >= 1)
            sens[(rw, hw)][ck] = round(qLH / n * 100, 2)
    return sens


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    # Parse args
    input_path = None; output_path = None; dict_path = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--dict' and i + 1 < len(args):
            dict_path = args[i + 1]; i += 2
        elif input_path is None:
            input_path = args[i]; i += 1
        elif output_path is None:
            output_path = args[i]; i += 1
        else:
            i += 1
    input_path = input_path or 'metamong_391sessions_deduped.json'
    output_path = output_path or 'bs_v22_results.json'

    # Load dictionary
    print(f"Loading dictionary...")
    raw_dict = load_dictionary(dict_path)
    C = compile_dict(raw_dict)
    print(f"Dictionary v{raw_dict['_meta']['version']} loaded: {len(C['AGREE'])} agree, {len(C['RESIST'])} resist, {len(C['ELAB_RE'])} elab_regex")

    # Load data
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    sessions = [s for s in data if len(s.get('relays', [])) > 0]
    total_relays = sum(len(s['relays']) for s in sessions)
    print(f"Loaded {len(sessions)} sessions, {total_relays} relays")

    # Assign conditions
    for s in sessions:
        s['cond'] = assign_condition(s, C)

    # Run
    print("Running v2.2 analysis...")
    results = analyze(sessions, C)
    sens = sensitivity_analysis(sessions, C)

    # Print
    print(f"\n{'='*95}")
    print(f"BS Analyzer v2.2 Results (dict: {raw_dict['_meta']['version']})")
    print(f"{'='*95}")
    print(f"\n{'조건':<18} {'세션':>4} {'릴레이':>6} {'응답(자)':>7} {'아첨강도':>7} {'환각%':>6} {'정교화%':>7} {'강%':>5} {'LH%':>6} {'1k자당':>7}")
    print("─" * 80)
    for ck in C['COND_ORDER']:
        r = results.get(ck)
        if not r: continue
        print(f"{r['label']:<18} {r['sessions']:>4} {r['relays']:>6} {r['avg_sys_len']:>7} {r['avg_syc']:>7.3f} {r['halluc_pct']:>6.2f} {r['elab_pct']:>7.2f} {r['elab_strong_pct']:>5.2f} {r['qLH_pct']:>6.2f} {r['rate_1k']:>7.4f}")

    # Verdict
    print(f"\n{'='*95}")
    print("Verdict Distribution")
    print(f"{'='*95}")
    print(f"\n{'조건':<18} {'drowning':>9} {'headway':>9} {'doldrums':>9} {'unclass':>9} {'hw_hi':>6} {'dr_hi':>6}")
    print("─" * 70)
    totals = {'d': 0, 'h': 0, 'dl': 0, 'u': 0, 'hh': 0, 'dh': 0}
    for ck in C['COND_ORDER']:
        r = results.get(ck)
        if not r: continue
        n = r['relays']
        print(f"{r['label']:<18} {r['v_drowning']:>5}({r['v_drowning']/n*100:>4.1f}%) {r['v_headway']:>5}({r['v_headway']/n*100:>4.1f}%) {r['v_doldrums']:>5}({r['v_doldrums']/n*100:>4.1f}%) {r['v_unclass']:>5}({r['v_unclass']/n*100:>4.1f}%) {r['v_hw_hi']:>6} {r['v_dr_hi']:>6}")
        totals['d'] += r['v_drowning']; totals['h'] += r['v_headway']
        totals['dl'] += r['v_doldrums']; totals['u'] += r['v_unclass']
        totals['hh'] += r['v_hw_hi']; totals['dh'] += r['v_dr_hi']
    t = total_relays
    print("─" * 70)
    print(f"{'합계':<18} {totals['d']:>5}({totals['d']/t*100:>4.1f}%) {totals['h']:>5}({totals['h']/t*100:>4.1f}%) {totals['dl']:>5}({totals['dl']/t*100:>4.1f}%) {totals['u']:>5}({totals['u']/t*100:>4.1f}%) {totals['hh']:>6} {totals['dh']:>6}")

    # Sensitivity
    print(f"\n{'='*95}")
    print("Sensitivity LH% ranking")
    for (rw, hw), cond_vals in sens.items():
        ranks = sorted(cond_vals.items(), key=lambda x: -x[1])
        print(f"  ({rw},{hw}): {' > '.join(f'{ck}({v:.2f}%)' for ck, v in ranks)}")

    # Save
    output = {
        'version': 'BS_Analyzer_v2.2_python',
        'dictionary_version': raw_dict['_meta']['version'],
        'total_sessions': len(sessions),
        'total_relays': total_relays,
        'conditions': results,
        'sensitivity': {f"R{rw}_H{hw}": v for (rw, hw), v in sens.items()}
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")
