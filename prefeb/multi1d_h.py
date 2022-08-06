import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 14}
text_font = {'family': 'Palatino Linotype', 'fontsize': 14}

# Data, x<idx_of_figure><idx_of_line>
x11 = []
x12 = []
x21 = []
x22 = []

y11 = []
y12 = []
y21 = []
y22 = []

# Data, position of text in subfigure 1
x_text = 0
y_text = 0

# Data, position of arrow in subfigure 1
x_arrow_start = 0
y_arrow_start = 0
x_arrow_end = 0
y_arrow_end = 0

# Plot
fig, axs = plt.subplots(1, 2, figsize=(8, 4))
    
# Subfig 1
axs[0].plot(x11, y11, label='label1', color=cm.Set2(0), marker='^', lw=2)
axs[0].plot(x12, y12, label='label2', color=cm.Set2(1), marker='o', lw=2)

axs[0].text(x_text, y_text, 'text', fontdict=text_font, color=cm.Set2(0), verticalalignment='center', horizontalalignment='left')
axs[0].annotate('', xy=(x_arrow_start, y_arrow_start), xytext=(x_arrow_end, y_arrow_end), arrowprops=dict(arrowstyle='->', facecolor=cm.Set2(0), edgecolor=cm.Set2(0)))

axs[0].set_xlabel('xlabel', fontdict=label_font)
axs[0].set_ylabel('ylabel', fontdict=label_font)
axs[0].set_title('title', fontdict=title_font)

# If customize ticks
# xticks = []
# yticks = []
# axs[0].set_xticks(xticks)
# axs[0].set_yticks(yticks)

# If customize scale
# axs[0].set_yscale('linear')
# axs[0].set_xscale('linear')

# If use sci notation
# axs[0].ticklabel_format(style='sci', scilimits=(-1, 2), axis='x')
# axs[0].ticklabel_format(style='sci', scilimits=(-1, 2), axis='y')

axs[0].legend(loc='upper right', prop=legend_font)
axs[0].grid(axis='both', color='black', alpha=0.1)
axs[0].tick_params(axis='both', which='major', labelsize=18)

# Subfig 2
axs[1].plot(x21, y21, label='label1', color=cm.Set2(0), marker='^', lw=2)
axs[1].plot(x22, y22, label='label2', color=cm.Set2(1), marker='o', lw=2)

axs[1].set_xlabel('xlabel', fontdict=label_font)
# axs[1].set_ylabel('ylabel', fontdict=label_font) # Uncomment if ylabel is not shared
axs[1].set_title('title', fontdict=title_font)

# If customize ticks
# xticks = []
# yticks = []
# axs[1].set_xticks(xticks)
# axs[1].set_yticks(yticks)

# If customize scale
# axs[1].set_yscale('linear')
# axs[1].set_xscale('linear')

# If use sci notation
# axs[1].ticklabel_format(style='sci', scilimits=(-1, 2), axis='x')
# axs[1].ticklabel_format(style='sci', scilimits=(-1, 2), axis='y')

axs[1].legend(loc='upper right', prop=legend_font)
axs[1].grid(axis='both', color='black', alpha=0.1)
axs[1].tick_params(axis='both', which='major', labelsize=18)

# Set label fontfamily
for i in range(2):
    labels = axs[i].get_xticklabels() + axs[i].get_yticklabels()
    [label.set_fontname('serif') for label in labels]

plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
