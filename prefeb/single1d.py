import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 18}

# Data
x1 = []
y1 = []
x2 = []
y2 = []

# Plot
fig, axs = plt.subplots(1, figsize=(4, 4))
    
axs.plot(x1, y1, label='label1', color=cm.Set2(0), marker='^', lw=2)
axs.plot(x2, y2, label='label2', color=cm.Set2(1), marker='o', lw=2)

axs.set_xlabel('xlabel', fontdict=label_font)
axs.set_ylabel('ylabel', fontdict=label_font)
axs.set_title('title', fontdict=title_font)

# If customize ticks
# xticks = []
# yticks = []
# axs.set_xticks(xticks)
# axs.set_yticks(yticks)

# If customize scale
# axs.set_xscale('linear')
# axs.set_yscale('linear')

# If use sci notation
# axs.ticklabel_format(style='sci', scilimits=(-1, 2), axis='x')
# axs.ticklabel_format(style='sci', scilimits=(-1, 2), axis='y')

axs.grid(axis='both', color='black', alpha=0.1)
axs.tick_params(axis='both', which='major', labelsize=18)

# Set label fontfamily 
labels = axs.get_xticklabels() + axs.get_yticklabels()
[label.set_fontname('serif') for label in labels]

# Uncomment if you want put the legend inside the fig
# axs.legend(loc='upper right', prop=legend_font)

# Set legned location (if put the legend outside the fig)
handles, labels = axs.get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', ncol=int(len(labels)/1), bbox_to_anchor=(0.5, -0.15), prop=legend_font)

plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
