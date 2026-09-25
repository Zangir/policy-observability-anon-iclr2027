"""Model-gap intervals from the planned and simultaneous sensitivity analyses."""
from pathlib import Path
import json
import matplotlib.pyplot as plt
from paper_style import style
ROOT=Path(__file__).resolve().parents[1]
def main():
 style();plt.rcParams.update({'font.size':12,'axes.labelsize':12,'xtick.labelsize':11,'ytick.labelsize':12,'legend.fontsize':11})
 d=json.loads((ROOT/'results/review_openai_v1.json').read_text())['rank_analysis'];a=json.loads((ROOT/'results/review_openai_v1_review_scaffold_audit.json').read_text())['simultaneous_gap_analysis']
 conditions=['reconsider','observe','ledger','validate'];labels=['Reconsider','Request reobservation','Provenance reminder','Validate same model']
 fig,ax=plt.subplots(figsize=(7.1,3.3))
 for i,(source,interval,label,color) in enumerate([(d,'ci95','Planned pointwise 95%','#0072B2'),(a,'simultaneous_ci95','Simultaneous sensitivity','#D55E00')]):
  stats=[source['per_scaffold'][c] for c in conditions];points=[s['difference']*100 for s in stats];lo=[max(0,100*(s['difference']-s[interval][0])) for s in stats];hi=[max(0,100*(s[interval][1]-s['difference'])) for s in stats]
  ax.errorbar(points,[j+(i-.5)*.2 for j in range(4)],xerr=[lo,hi],fmt='o' if i==0 else 's',color=color,label=label,capsize=3)
 ax.set_xlim(-1,1);ax.set_xticks([-1,-.5,0,.5,1]);ax.axvline(0,color='#555555',linestyle='--',linewidth=1);ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlabel('Sol minus Luna balanced accuracy (percentage points)');ax.grid(axis='y',visible=False);ax.legend(loc='upper center',bbox_to_anchor=(.5,1.23),ncol=2);fig.tight_layout()
 for ext in ['pdf','png']:fig.savefig(ROOT/'figures'/('review_scaffold_gaps.'+ext),bbox_inches='tight')
 (ROOT/'results/review_scaffold_gap_figure.json').write_text(json.dumps({'planned':d,'simultaneous':a},indent=2)+'\n')
if __name__=='__main__':main()
