"""Conditional authorized utility and unauthorized proposal rates."""
from pathlib import Path
import json
import matplotlib.pyplot as plt
from paper_style import style
ROOT=Path(__file__).resolve().parents[1]
def main():
 style();plt.rcParams.update({'font.size':13,'axes.labelsize':13,'axes.titlesize':13,'xtick.labelsize':12,'ytick.labelsize':12,'legend.fontsize':12})
 d=json.loads((ROOT/'results/review_openai_v1_review_authorization_audit.json').read_text())
 conditions=['caution_neutral','caution_claim','ledger_neutral','ledger_claim'];labels=['Caution / neutral','Caution / claim','Ledger / neutral','Ledger / claim']
 fig,axes=plt.subplots(1,2,figsize=(8.4,3.7),sharey=True)
 values=[]
 for ax,title,field,metric in zip(axes,['Authorized execution','Unauthorized EXECUTE proposal'],['authorized_summary','unauthorized_summary'],['correct','unsafe_proposal']):
  for i,m in enumerate(['gpt-5.6-luna','gpt-5.6-sol']):
   stats=[d[field][m][c][metric] for c in conditions];x=[100*s['mean'] for s in stats];lo=[max(0,100*(s['mean']-s['ci95'][0])) for s in stats];hi=[max(0,100*(s['ci95'][1]-s['mean'])) for s in stats];y=[j+(i-.5)*.20 for j in range(4)]
   ax.errorbar(x,y,xerr=[lo,hi],fmt='o' if i==0 else 's',color=['#0072B2','#D55E00'][i],label=['Luna','Sol'][i],capsize=3)
   values.append({'field':field,'model':m,'conditions':conditions,'stats':stats})
  ax.set_xlim((-3,103) if metric=='correct' else (-.15,5));ax.set_xticks([0,25,50,75,100] if metric=='correct' else [0,1,2,3,4,5]);ax.set_title(title);ax.set_xlabel('Conditional rate (%)');ax.set_yticks(range(4),labels);ax.grid(axis='y',visible=False)
 axes[0].invert_yaxis();handles,names=axes[0].get_legend_handles_labels();fig.legend(handles,names,loc='lower center',ncol=2,bbox_to_anchor=(.5,-.07));fig.tight_layout(rect=[0,.05,1,1])
 for ext in ['pdf','png']:fig.savefig(ROOT/'figures'/('review_authorization_audit.'+ext),bbox_inches='tight')
 (ROOT/'results/review_authorization_figure.json').write_text(json.dumps(values,indent=2)+'\n')
if __name__=='__main__':main()
