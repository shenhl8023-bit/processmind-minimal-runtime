"""Compile reviewed Word curation into local-search JSON with source anchors."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from word_knowledge_curation import RULES, ALLOWANCES, ROUTES, DIAGRAMS, CONDITIONAL

BASE = Path(__file__).resolve().parents[1]
DEMO = BASE / 'knowledge/demo'
ROOT = DEMO / 'word_sources'

def load_sources():
    return json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))

def build(output: Path):
    sources = load_sources()
    docs = {}
    for s in sources:
        assert hashlib.sha256((BASE / s['source_path']).read_bytes()).hexdigest() == s['sha256']
        anchor_data = json.loads((ROOT / s['id'] / 'anchors.json').read_text(encoding='utf-8'))
        blocks = {b['id']: b for b in anchor_data['blocks']}
        docs[s['id']] = (s, blocks, anchor_data)
    records, coverage, issues = [], [], []
    record_counts = {}
    def record(sid, anchor, kind, title, topics, conditions, conclusion='', status='verified', metrics=None, exception='', family=None, typical=None, excerpt=None, resource=None, conflict=None, category='process_guidance'):
        s, blocks, data = docs[f'WD{sid:02}']
        paras=[]
        for p in ([] if '.png' in anchor else re.findall(r'\d+', anchor)):
            b=blocks.get(f'P{int(p):03}')
            if b and b.get('text','').strip(): paras.append((f'P{int(p):03}',b['text'].strip()))
        identity=', '.join(f'{s["document_number"]}:{a}' for a,_ in paras)
        if not paras and '.png' in anchor: identity=f'{s["document_number"]}:{anchor}'
        original=excerpt if excerpt is not None else ' '.join(t for _,t in paras)
        if not conclusion: conclusion=original
        g={'kind':kind,'applicability':s['applicability'],'part_family':family or s['part_family'],'typical_part':typical or s['typical_part'],'materials':s['materials'],'topics':topics.split(','),'conditions':conditions,'conclusion':conclusion,'exceptions':exception,'verification_status':status,'original_excerpt':original}
        if metrics: g['metrics']=metrics
        if resource: g['resources']=resource
        base_id=f'{s["id"]}-{anchor.split(",")[0]}-{kind}'
        record_counts[base_id]=record_counts.get(base_id,0)+1
        rid=base_id if record_counts[base_id]==1 else f'{base_id}-{record_counts[base_id]:02}'
        r={'id':rid,'category':category,'title':title,'fields':{'内容':conclusion,'主题':topics,'适用条件':conditions},'source':{'document_id':s['id'],'document_name':s['file_name'],'identity':identity,'page_no':None},'guidance':g}
        if conflict: r['conflict_ids']=[conflict]
        if sid == 1 and anchor == '53' and kind == 'allowance' and '密封槽边' in title:
            r['issue_ids']=['WD01-numeric']
            r['data_warnings']=['原文0.8mm上限待核对；此记录保留原值。']
        if kind == 'formula':
            r['guidance']['conditions'] += '；公式仅作原文语义解释，不进行自动计算。'
            r['guidance']['exceptions'] += ' 本记录仅解释公式，不提供自动计算能力。'
        records.append(r)
        return rid
    # Rules and source references
    for sid, anchors, kind, title, topics, cond, conclusion in RULES:
        status='pending' if (sid==1 and anchors=='53') or (sid==8 and anchors=='50') or (sid in (6,7) and anchors in ('24,27','23,26')) else 'verified'
        exception='原文措辞/上下文需专家核对；来源一致性不代表批准或现行有效。' if status=='pending' else '按本典型对象及原文条件使用；不得外推到未说明对象或设计要求。'
        record(sid,anchors,'reference' if kind=='reference' else kind,title,topics,cond,conclusion,status=status,exception=exception)
    for sid, p, name, lo, hi, unit, basis, direction in ALLOWANCES:
        status='pending' if (sid==1 and p==53 and (lo,hi)==(.04,.8)) else 'verified'
        note='原文0.8上限疑似异常，数值原样保留并待核对。' if status=='pending' else '只适用于所述对象、工序阶段和口径；不得泛化图纸公差。'
        record(sid,str(p),'allowance',name+'余量/控制',name, f'{name}；{basis}', status=status, metrics=[{'name':name,'min':lo,'max':hi,'unit':unit,'basis':basis,'direction':direction}], exception=note)
    for name, lo, hi, basis in [('粗加工时配套内孔对外圆跳动',.02,.4,'钢衬套正文P058；原文范围可疑，待核对'),('淬火后配套内孔对外圆跳动',.05,.1,'钢衬套正文P058')]:
        rid=record(1,'58','quality',name,'跳动,淬火,粗加工,热处理',f'钢件衬套2219.026F及所述粗加工/淬火阶段；{basis}',f'正文给出的跳动范围{lo}—{hi}mm，待结合设计图及原文核对。' if hi==.4 else f'正文给出的跳动范围{lo}—{hi}mm。',status='pending' if hi==.4 else 'verified',metrics=[{'name':name,'min':lo,'max':hi,'unit':'mm','basis':basis,'direction':'控制范围'}],exception='原文保留数值，不泛化为全族设计公差。')
        if hi==.4:
            records[-1]['issue_ids']=['WD01-numeric'];records[-1]['data_warnings']=['原文0.4mm上限待核对。']
    # Internal steel sleeve body vs attachment hardness conflict, both searchable members.
    conflict='WD01-tempering-hardness'
    record(1,'58','quality','钢衬套调质硬度正文值','调质,硬度,9Cr18', '钢衬套正文P058调质处理', '22—32HRC（正文值），需与附件示例核对。', status='conflict', metrics=[{'name':'调质硬度','min':22,'max':32,'unit':'HRC','basis':'钢衬套正文P058'}], exception='同一说明附件工艺卡P083 image3给27—35HRC；不得单独作为定值依据。', conflict=conflict)
    record(1,'image3.png','quality','钢衬套调质硬度附件示例值','调质,硬度,9Cr18', '2219.026F附件工艺卡示例P083 image3', '27—35HRC（附件工艺卡示例），需与正文核对。', status='conflict', metrics=[{'name':'调质硬度','min':27,'max':35,'unit':'HRC','basis':'附件P083工艺卡示例'}], exception='正文P058给22—32HRC；仅为填写示例，不代表适用设计要求。', conflict=conflict, excerpt='附件P083 image3：工艺卡硬度HRC27~35；技术要求“热处理HRC27~35”。')
    for name, anch, model, category in [('钻孔','image8.png','Z512','equipment'),('珩孔','image10.png','MC1805','equipment'),('磨外圆','image13.png','S21','equipment'),('检验','image11.png','卡尺0.02；千分尺0.01；专用塞规/环规；10倍放大镜','gauge')]:
        record(1,anch,'resource',f'钢衬套{name}卡片图示资源','工序卡,资源,'+name, f'2219.026F {name}工序工艺卡填写示例；设备/量具型号来自图片，不证明通用能力。', f'图示{model}。此为特定工序卡示例资源，非设备能力或通用工艺要求。',exception='型号、配用工序及适用范围应按实际工艺卡/设备台账确认；不得据此推断加工能力。',resource=[{'category':category,'name':name,'model':model,'identifier':'','basis':f'附件图片 {anch}'}],excerpt=f'钢衬套2219.026F工艺卡图示：{name}，{model}。')
    record(1,'58','quality','钢衬套9Cr18淬火常用硬度范围','淬火,硬度,9Cr18','钢衬套典型材料9Cr18；粗加工后淬火','9Cr18淬火硬度常用58—62HRC，具体按设计图纸要求。',metrics=[{'name':'9Cr18淬火硬度','min':58,'max':62,'unit':'HRC','basis':'钢衬套正文P058；常用值，依设计图'}],exception='不同材料/图纸要求优先；不得与调质硬度冲突组混同。')
    # Drawing callouts belong only to the named specimen and remain source-specific.
    for sid, image, values in [
        (2,'image1.png',[('外圆表面粗糙度',.4,'μm'),('圆柱度',.002,'mm')]),
        (3,'image1.png',[('图示间隙',.010,.015,'mm'),('局部表面粗糙度',.16,'μm'),('局部表面粗糙度',.32,'μm')]),
        (4,'image1.png',[('配套外圆表面粗糙度',.4,'μm'),('圆柱度',.002,'mm')]),
        (5,'image1.png',[('配套孔表面粗糙度',.4,'μm'),('圆柱度',.002,'mm')]),
    ]:
        for item in values:
            if len(item)==4: name, lo, hi, unit=item
            else: name, lo, unit=item; hi=lo
            record(sid,image,'reference',f'{docs[f"WD{sid:02}"][0]["typical_part"]}结构图{name}','结构图,设计指标,'+name,'仅适用于该典型零件结构图示；不作为产品族默认值或设备能力。',f'原图标注{name} {lo}'+(f'—{hi}' if hi!=lo else '')+f' {unit}。',metrics=[{'name':name,'min':lo,'max':hi,'unit':unit,'basis':f'原始结构图 {image}；仅示例图纸指标'}],exception='图纸示例尺寸/几何要求必须由实际产品设计图确认，不泛化至产品族。')
    for sid in (6,7,8):
        record(sid,'image1.png','reference',f'{docs[f"WD{sid:02}"][0]["typical_part"]}典型零件结构图','结构图,零件结构','仅为典型对象的结构图；不从结构截图自动提取或泛化未核实的尺寸/公差。','源文件嵌入结构图，保留本地原图供逐项核对。',exception='未将不清晰/特定图纸标注转成族级规则。',excerpt='典型零件结构图；未提取为族级尺寸/公差规则。')
    # The evaluation table is historical editorial metadata, not process capability.
    eval_id=record(1,'65','reference','钢衬套典型工艺成熟度评价表口径','成熟度评价,NA,评分','仅记录本文件历史自评结果，不代表现行有效性、知识正确性或制造能力。','正文P065写得分37（82%）；表T01R13合计列标准分50、得分37；T01R11第9项NA，表注T01R16说明NA不计入。按45分有效项计算37/45≈82.2%，与正文82%近似但口径需核对。',status='pending',exception='评价表不得作为工艺规则、设备能力或现行成熟度依据。',excerpt='P065：得分37（82%）。T01R13：标准分50、实得37。T01R11：NA；T01R16：NA不记入。')
    records[-1]['source']['identity']='05-JB50-21:P065; '+', '.join(f'T01R{n:02}' for n in range(3,17))
    # Only routes whose arrow order was visibly legible are transcribed as sequences.
    for sid, anchors, stages, notes in ROUTES:
        source_anchor=anchors.split(',')[0]
        diagram=DIAGRAMS.get(sid)
        if diagram:
            image, image_paragraph, sequence = diagram
            rid=record(sid,image,'route',f'{docs[f"WD{sid:02}"][0]["typical_part"]}典型路线（图示顺序）','典型路线,工序阶段','按嵌入路线图箭头次序逐节点转录；重复工序保留为独立步骤。','→'.join(sequence),status='verified',exception=notes,category='typical_route')
            r=records[-1]; r['guidance']['completeness']='verified_sequence'; r['guidance']['operations']=[]
            route_text_anchor={2:'P031',5:'P032,P041',6:'P043',7:'P034',8:'P044'}[sid]
            r['source']['identity']=f'{docs[f"WD{sid:02}"][0]["document_number"]}:{route_text_anchor}; {image_paragraph} {image}'
            for ix, name in enumerate(sequence,1):
                bare=name.split('(')[0]
                state=CONDITIONAL.get(sid,{}).get(bare,'required')
                condition='图中标注虚拟，仅为产品族模板参考。' if state=='virtual' else ('图中标注按需，依结构/设计条件选择。' if state=='conditional' else '路线图箭头顺序中的步骤。')
                r['guidance']['operations'].append({'id':f'{rid}-op{ix:02}','sequence':ix,'number':'','name':name,'execution_status':state,'condition':condition,'source':{'document_id':f'WD{sid:02}','document_name':docs[f'WD{sid:02}'][0]['file_name'],'identity':f'{docs[f"WD{sid:02}"][0]["document_number"]}:{image_paragraph} {image}','page_no':None}})
            continue
        route_status='pending' if sid in (3,4) else 'verified'
        rid=record(sid,anchors,'stage_overview',f'{docs[f"WD{sid:02}"][0]["typical_part"]}典型路线（阶段概要）','典型路线,工序阶段', '本典型对象；概要基于正文及可核图示；不代表完整工序序列。',stages,status=route_status,exception=notes,category='typical_route')
        r=records[-1]; r['guidance']['completeness']='stage_overview'; r['guidance']['operations']=[]
        if sid==4:
            r['conflict_ids']=['WD04-route']
        if sid==8:
            r['source']['identity'] += '; P043,P044,P045,P046'
        if sid==1:
            r['source']['identity'] += '; P043-P051'
        for ix, stage in enumerate(stages.split('→'),1):
            r['guidance']['operations'].append({'id':f'{rid}-op{ix:02}','sequence':ix,'number':'','name':stage.strip(),'execution_status':'required','condition':'典型路线阶段概要；具体工序以适用条件、图纸及工艺卡为准。','source':{'document_id':f'WD{sid:02}','document_name':docs[f'WD{sid:02}'][0]['file_name'],'identity':f'{docs[f"WD{sid:02}"][0]["document_number"]}:P{int(source_anchor):03}','page_no':None}})
        supplemental = {
            1:[('去应力','conditional','P046'),('磨槽','conditional','P047'),('线切割/电火花','conditional','P048'),('光整表面','conditional','P049'),('时效','conditional','P050'),('钝化','conditional','P051'),('研磨','conditional','P062')],
            2:[('磨槽','virtual','P032'),('冲洗','conditional','P033'),('研外圆','conditional','P044')],
            3:[('车外形','conditional','P041'),('冲洗','conditional','P033'),('低温灵活性试验','virtual','P054')],
            4:[('冲洗','conditional','P059'),('硬质阳极化','required','P071')],
            5:[('硬质阳极化','required','P041'),('研磨','conditional','P048')],
            6:[('去应力','conditional','P043'),('研外圆','conditional','P050')],
            7:[('去应力','conditional','P043'),('研孔','conditional','P046')],
            8:[('去应力','conditional','P045'),('裂纹检查/烧伤检查','conditional','P054'),('研外圆','conditional','P056')],
        }[sid]
        for name, state, para in supplemental:
            text = docs[f'WD{sid:02}'][1][para]['text'].strip()
            r['guidance']['operations'].append({'id':f'{rid}-cond-{para}-{len(r["guidance"]["operations"])}','sequence':0,'number':'','name':name,'execution_status':state,'condition':text,'source':{'document_id':f'WD{sid:02}','document_name':docs[f'WD{sid:02}'][0]['file_name'],'identity':f'{docs[f"WD{sid:02}"][0]["document_number"]}:{para}','page_no':None}})
    wd03_chart=record(3,'image2.png','route','RT34(03)-100路线图顺序（待核）','典型路线,配套,配研,浸泡,超声波冲洗,冲洗,低温灵活性试验','图示箭头顺序逐节点转录；与P032文字概述的末端顺序存在差异。','→'.join(['备件','清洗','检验','车外形','车外形','车外形','去毛刺','配套','配研外圆','浸泡','超声波冲洗','冲洗','清洗','检验','选配','低温灵活性试验','清洗','检验','油封']),status='pending',exception='P032末尾把清洗、低温灵活性试验、油封合并描述；图P030显示选配后低温试验（虚拟）、清洗、检验、油封。不得把图文差异静默合并。',category='typical_route')
    wd03_chart=records[-1]
    wd03_chart['conflict_ids']=['WD03-route-order']
    wd03_chart['guidance']['completeness']='verified_sequence'
    wd03_chart['guidance']['operations']=[]
    wd03_steps=['备件','清洗','检验','车外形','车外形','车外形','去毛刺','配套','配研外圆','浸泡','超声波冲洗','冲洗','清洗','检验','选配','低温灵活性试验','清洗','检验','油封']
    for ix,name in enumerate(wd03_steps,1):
        state='virtual' if name=='低温灵活性试验' else ('conditional' if name in ('车外形','去毛刺','冲洗') else 'required')
        wd03_chart['guidance']['operations'].append({'id':f'{wd03_chart["id"]}-op{ix:02}','sequence':ix,'number':'','name':name,'execution_status':state,'condition':'图示标注虚拟/按需，需对照产品条件。' if state!='required' else '路线图箭头顺序中的步骤。','source':{'document_id':'WD03','document_name':docs['WD03'][0]['file_name'],'identity':'69-JB20-21:P030 image2.png','page_no':None}})
    for r in records:
        if r['category']=='typical_route' and r['source']['document_id']=='WD03':
            r.setdefault('conflict_ids',[]).append('WD03-route')
            r['guidance']['verification_status']='conflict'
        if r['category']=='typical_route' and r['source']['document_id']=='WD08':
            r.setdefault('conflict_ids',[]).append('WD08-check-semantics')
            r['guidance']['verification_status']='conflict'
        if r['category']=='typical_route' and r['source']['document_id']=='WD05':
            r['conflict_ids']=['WD05-route']
            r['guidance']['verification_status']='conflict'
    wd08_check=next(r for r in records if r['source']['document_id']=='WD08' and r['source']['identity'].endswith(':P054'))
    wd08_check.setdefault('conflict_ids',[]).append('WD08-check-semantics')
    wd08_check['guidance']['verification_status']='conflict'
    formula_component=next(r for r in records if r['source']['document_id']=='WD03' and r['guidance']['kind']=='formula')
    formula_component['source']['identity']='69-JB20-21:P041; P040 image3.png'
    # Source issues preserve questionable source values and wording.
    for id_, recids, sid, desc, vals, locations in [
        ('WD01-hardness', [r['id'] for r in records if r.get('conflict_ids')==[conflict]],'WD01','钢衬套正文调质硬度与附件工艺卡示例不一致，双方保留。',['22—32HRC','27—35HRC'],['P058','P083 image3']),
        ('WD01-score', [eval_id],'WD01','正文成熟度37分/82%与表格标准50分、NA不计入的有效分母口径存在差异。',['37/50','37/45≈82.2%'],['P065','T01R03-R16']),
        ('WD01-numeric', [r['id'] for r in records if 'WD01-numeric' in r.get('issue_ids',[])],'WD01','钢衬套0.4mm跳动上限及0.8mm槽边余量原文可疑，需核对，不擅改小数点。',['0.02—0.4mm','0.04—0.8mm'],['P053','P058']),
        ('WD06-material', [r['id'] for r in records if r['source']['document_id']=='WD06' and 'P027' in r['source']['identity']],'WD06','材料牌号QAL10-4-4原文照录，标准拼写待核。',['QAL10-4-4'],['P027']),
        ('WD07-material', [r['id'] for r in records if r['source']['document_id']=='WD07' and 'P026' in r['source']['identity']],'WD07','材料牌号QA110-4-4原文照录，标准拼写待核。',['QA110-4-4'],['P026']),
        ('WD08-wording', [r['id'] for r in records if r['source']['document_id']=='WD08' and 'P050' in r['source']['identity']],'WD08','锐边段落写“精密钢件淬火类活门”，与本文件氮化/氰化标题和典型对象关系需复核。',['精密钢件淬火类活门'],['P050']),
        ('WD04-route', [r['id'] for r in records if r['category']=='typical_route' and r['source']['document_id']=='WD04'],'WD04','P058阶段概要未列硬质阳极化，P071写在半精去铬酸层后进行；图形XML按形状提取不能还原箭头顺序。',['P058与P071/P043'],['P031','P043','P058','P071']),
        ('WD05-route', [r['id'] for r in records if r['category']=='typical_route' and r['source']['document_id']=='WD05'],'WD05','P032阶段概要未列硬质阳极化；P030图示及P041文字显示该处理步骤。完整图示序列保留，概要差异待人工核对。',['P032与P030/P041'],['P030','P032','P041']),
        ('WD03-route', [r['id'] for r in records if 'WD03-route' in r.get('conflict_ids',[])],'WD03','组件正文末尾概述与P030路线图低温试验后清洗、检验顺序存在差异；图示路线与文字阶段概述分开保留。',['正文与图片顺序差异'],['P030','P032','P054']),
        ('WD08-check-semantics', [r['id'] for r in records if 'WD08-check-semantics' in r.get('conflict_ids',[])],'WD08','P041图将烧伤检查标为虚拟，而P054要求渗氮后每道磨削首件做烧伤检查，末道额外检查才按需。两者语境需人工确认。',['路线图虚拟','每道磨削首件必检','末道之后额外检查按需'],['P041 image2.png','P054'])]:
        issues.append({'id':id_,'record_ids':recids,'source_ids':[sid],'description':desc,'original_values':vals,'locations':locations,'status':'pending'})
    # Coverage includes every paragraph/table row and every image; empty and administrative items explained.
    for s, blocksdata in ((s, docs[s['id']][2]) for s in sources):
        for b in blocksdata['blocks']:
            anchor=b['id']; txt=b.get('text','').strip()
            covered=[r['id'] for r in records if r['source']['document_id']==s['id'] and (anchor in r['source']['identity'])]
            if b['type']=='table':
                for row in b['rows']:
                    row_ids=[r['id'] for r in records if r['source']['document_id']==s['id'] and row['id'] in r['source']['identity']]
                    coverage.append({'source_id':s['id'],'anchor':row['id'],'disposition':'included' if row_ids else 'excluded','record_ids':row_ids,'reason':'' if row_ids else '历史成熟度评价或表头数据；仅保留为本地源表，不编码为制造能力/工艺规则。'})
            else:
                disp='included' if covered else ('empty' if not txt else 'excluded')
                administrative = anchor in ('P005','P006','P008','P010','P017','P018','P019','P020')
                if not txt:
                    reason='空段落，仅保留定位。'
                elif covered:
                    reason=''
                elif administrative:
                    reason='封面、签署或编制人员/日期元数据，只用于来源追溯；不作为能力或有效性结论。'
                elif s['id']=='WD01' and anchor in {f'P{n:03}' for n in range(31,42)}:
                    related=[r['id'] for r in records if r['source']['document_id']=='WD01' and (r['category']=='typical_route' or r['guidance']['kind']=='rule')]
                    coverage.append({'source_id':s['id'],'anchor':anchor,'disposition':'excluded','record_ids':related,'reason':'该段是嵌入路线图的VML/DrawingML文本框顺序化提取，不等同于图上箭头方向；主路线采用P044正文，按需条件依据P046-P051策展。'})
                    continue
                elif s['id']=='WD04' and anchor in {f'P{n:03}' for n in range(31,47)}:
                    related=[r['id'] for r in records if r['source']['document_id']=='WD04' and r['category']=='typical_route']
                    coverage.append({'source_id':s['id'],'anchor':anchor,'disposition':'excluded','record_ids':related,'reason':'该段为硬阳化路线图形XML的文本框提取；DrawingML/VML重复节点的存储顺序不是可核路线。保留图形锚点，阶段概要据P058/P067/P071，并显式列入路线差异待核。'})
                    continue
                elif re.match(r'^(\d+(\.\d+)*\s*)?(适用范围|典型零件|典型零件工艺规程设计|工序编制说明|工艺路线如下|工艺路线说明|重叠量计算说明|典型工艺评价|其余技术要求|加工余量说明|锐边要求|热处理要求|标印|精加工配套|硬质阳极化要求|铬酸阳极化要求|裂纹检查及烧伤检查)', txt):
                    reason='章节/小节标题；该锚点没有独立工艺条件或结论（相邻正文规则另有记录）。'
                elif any(k in txt for k in ('工艺规程的编制按','工序的填写按','工序编制说明')):
                    reason='仅列出被引用但未提供全文的编制规范，不能据此编码未见正文的要求。'
                elif s['id']=='WD01' and anchor=='P045':
                    related=[r['id'] for r in records if r['source']['document_id']=='WD01' and r['guidance']['kind']=='rule']
                    coverage.append({'source_id':s['id'],'anchor':anchor,'disposition':'excluded','record_ids':related,'reason':'此为“增加8道按需工序”引导句；具体条件分别从P046-P051拆成已链接的去应力、磨槽、型孔、光整、时效、钝化规则。'})
                    continue
                elif txt in ('典型工艺说明','工序编制说明','图一','图1'):
                    reason='标题或图题；对应图像及相关规则另按图像/段落锚点处理。'
                else:
                    reason='保留全文于项目内锚点提取；本段为重复说明、示例零件图题或未形成可独立复用条件规则的内容，避免把图纸要求泛化。'
                coverage.append({'source_id':s['id'],'anchor':anchor,'disposition':disp,'record_ids':covered,'reason':reason})
        for fig in blocksdata['figures']:
            anch=fig['target'].split('/')[-1]
            ids=[r['id'] for r in records if r['source']['document_id']==s['id'] and anch in r['source']['identity']]
            coverage.append({'source_id':s['id'],'anchor':f'{fig["paragraph"]} {anch}','disposition':'included' if ids else 'excluded','record_ids':ids,'reason':'' if ids else ('结构图设计尺寸只属示例零件，不泛化为族规则；图片副本保留。' if 'image' in anch else '路线图仅作阶段概要依据，完整图可从项目本地副本复核。')})
    output.mkdir(parents=True,exist_ok=True)
    for name,data in [('records',records),('sources',sources),('issues',issues),('coverage',coverage)]:
        (output/f'word_{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return records,sources,issues,coverage

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEMO);args=parser.parse_args()
    data=build(args.output);print(json.dumps({k:len(v) for k,v in zip(('records','sources','issues','coverage'),data)},ensure_ascii=False))
