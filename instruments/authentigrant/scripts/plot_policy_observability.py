"""Plot the complete ambient-pressure model/condition decomposition."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
d=json.loads((ROOT/'results/external_report.json').read_text())
models=['glm-5','gpt-5.4','kimi-k2.5','minimax-m2.5']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(9.2,3.8),sharey=True)
colors=['#24688d','#d58936','#875b94']
for ax,condition,title in zip(axes,['prompt_only','guardrail'],['Prompt-only','Keyword filter']):
 rows=[next(x for x in d['historical_groups'] if x['condition']==condition and x['model']==m and x['pressure']=='P2') for m in models]
 left=np.zeros(4)
 for reason,color,label in zip(['tool_name','argument','history'],colors,['Tool names (shown)','Arguments (omitted)','History (omitted)']):
  values=np.array([100*r['violation_'+reason]/r['trials'] for r in rows]);ax.barh(np.arange(4),values,left=left,color=color,label=label,height=.62);left+=values
 for y,r,total in zip(range(4),rows,left):ax.text(total+.8,y,f"{r['violation_trials']}/{r['trials']}",va='center',fontsize=12)
 ax.set_title(title,fontsize=13);ax.set_xlim(0,49);ax.set_xticks([0,10,20,30,40]);ax.set_xlabel('Violating trials (%)');ax.set_axisbelow(True);ax.grid(axis='x',alpha=.17)
 axes[0].set_yticks(range(4),['GLM-5','GPT-5.4','Kimi-K2.5','MiniMax-M2.5'])
axes[0].invert_yaxis()
handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,fontsize=12,frameon=False)
fig.subplots_adjust(left=.16,right=.985,top=.88,bottom=.28,wspace=.12)
for target in [ROOT/'figures',ROOT.parents[1]/'paper/figures']:
 target.mkdir(exist_ok=True)
 fig.savefig(target/'external_policy_observability.pdf',bbox_inches='tight')
 fig.savefig(target/'external_policy_observability.png',dpi=180,bbox_inches='tight')
plt.close(fig)
