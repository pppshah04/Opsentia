"""Check v2 synthetic fixture joins and core stock-flow arithmetic."""
from pathlib import Path
import csv,sys,collections
root=Path(__file__).resolve().parent.parent
D=root/'data'
required=['synthetic_operations.csv','opsentia_incidents.csv','opsentia_notification_events.csv','opsentia_metric_baselines_30min.csv','opsentia_forecast_backtest.csv','opsentia_decision_scenario_inputs.csv']
missing=[n for n in required if not (D/n).exists()]
if missing:sys.exit('Missing: '+repr(missing))
with open(D/'synthetic_operations.csv',newline='',encoding='utf8') as f:
 r=csv.DictReader(f)
 unique=set(); count=0; queue=set(); errors=[]
 for x in r:
  count+=1; queue.add(x['queue']); key=(x['timestamp'],x['queue'])
  if key in unique:errors.append('duplicate '+str(key))
  unique.add(key)
  offered=int(float(x['offered_calls']));answered=int(float(x['answered_calls']));abandoned=int(float(x['abandoned_calls']));opening=int(float(x['backlog_opening']));closing=int(float(x['backlog']))
  if opening+offered != answered+abandoned+closing:errors.append('flow '+str(key))
  if int(float(x['sla_met_calls'])) > answered:errors.append('SLA denominator '+str(key))
  if not 0<=float(x['sla'])<=1:errors.append('SLA range '+str(key))
 if count!=43680:errors.append('unexpected row count '+str(count))
 if len(queue)!=5:errors.append('queue count '+str(len(queue)))
 if errors:sys.exit('FAIL: '+str(len(errors))+' bad rows: '+repr(errors[:10]))
 print('PASS synthetic_operations',count,'rows',len(queue),'queues; stock-flow, SLA, unique keys')
# Reconcile daily materialized totals with the interval source (queue-specific rows only).
try:
 import pandas as pd
 src=pd.read_csv(D/'synthetic_operations.csv',usecols=['timestamp','queue','offered_calls','answered_calls','abandoned_calls','sla_met_calls'])
 daily=pd.read_csv(D/'opsentia_daily_kpis.csv')
 src['date']=src['timestamp'].str[:10]
 agg=src.groupby(['date','queue'],as_index=False)[['offered_calls','answered_calls','abandoned_calls','sla_met_calls']].sum()
 merged=agg.merge(daily[daily['queue']!='All Queues'],on=['date','queue'],suffixes=('_source','_daily'),validate='one_to_one')
 if len(merged)!=len(agg):sys.exit('FAIL incomplete daily queue aggregation')
 for metric in ['offered_calls','answered_calls','abandoned_calls','sla_met_calls']:
  if not (merged[metric+'_source']==merged[metric+'_daily']).all():sys.exit('FAIL daily mismatch '+metric)
 if (((merged['sla_met_calls_source']/merged['answered_calls_source'].clip(lower=1))-merged['sla']).abs() > .0001).any():sys.exit('FAIL daily weighted SLA mismatch')
 if len(list(D.glob('*.csv')))!=26:sys.exit('FAIL expected 26 CSV fixtures')
 print('PASS daily reconciliation:',len(merged),'queue-days, 4 exact counts, weighted SLA; 26 files present')
except ImportError:
 sys.exit('pandas required for aggregate reconciliation; pip install -r requirements.txt')
