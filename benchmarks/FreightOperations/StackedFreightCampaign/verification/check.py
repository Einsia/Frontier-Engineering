import collections,csv,json,shutil,subprocess,tempfile
from pathlib import Path
if not shutil.which('java'):raise RuntimeError('Java checker runtime missing')
def evaluate(data,outputs):
 try:
  src=Path(data)/'campaign';out=Path(outputs);official=Path(__file__).parent/'official'
  expected=collections.Counter()
  with (src/'input_items.csv').open(encoding='latin1',newline='') as f:
   for r in list(csv.reader(f,delimiter=';'))[1:]:
    if r:expected[r[0]]+=int(r[7])
  with (out/'output_items.csv').open(encoding='latin1',newline='') as f:actual=collections.Counter(r[0] for r in list(csv.reader(f,delimiter=';'))[1:] if r)
  if actual!=expected:raise ValueError('Output item multiplicities must exactly match the input quantities')
  with tempfile.TemporaryDirectory() as tmp:
   t=Path(tmp);(t/'logs').mkdir()
   for n in ['items','trucks','parameters']:shutil.copy2(src/('input_'+n+'.csv'),t/('input_'+n+'.csv'))
   for n in ['items','stacks','trucks']:shutil.copy2(out/('output_'+n+'.csv'),t/('output_'+n+'.csv'))
   shutil.copy2(official/'logback.xml',t/'logback.xml')
   (t/'instances.csv').write_text('input items pathFilename;input trucks pathFilename;input parameters pathFilename;output items pathFilename;output stacks pathFilename;output trucks pathFilename;report pathFilename\n'+';'.join(str(t/n) for n in ['input_items.csv','input_trucks.csv','input_parameters.csv','output_items.csv','output_stacks.csv','output_trucks.csv','report.csv'])+'\n')
   q=subprocess.run(['java','-Xmx8g','-DLOG_FILENAME=logs/checker','-Dlogback.configurationFile=logback.xml','-jar',str(official.resolve()/'CheckerChallenge-1.11.4.jar'),'instances.csv'],cwd=t,capture_output=True,text=True,timeout=900)
   report=(t/'report.csv').read_text(encoding='latin1') if (t/'report.csv').exists() else ''
   rows=list(csv.reader(report.splitlines(),delimiter=';'))
   valid=q.returncode==0 and len(rows)==2 and rows[0][:3]==['transportation cost','inventory cost','objective function']
   if valid:
    costs=[float(x.replace(',','.')) for x in rows[1][:3]]
    return {'valid':True,'cases':{'campaign':{'valid':True,'transportation_cost':costs[0],'inventory_cost':costs[1],'objective':costs[2],'items':sum(actual.values())}}}
   return {'valid':False,'error':report[:12000] or (q.stdout+q.stderr)[-5000:] or 'Official checker did not emit a validity report'}
 except (OSError,ValueError,KeyError,TypeError) as e:return {'valid':False,'error':str(e)}
