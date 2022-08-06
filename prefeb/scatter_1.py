import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 14}

# Data
data_x = []
data_y = []
start, end = [0, 1], [0, 1]
title_list = ['(a)', '(b)', '(c)', '(d)']

# Plot
fig, axs = plt.subplots(2, 2, figsize=(8, 8))
    
for i in range(2):
    for j in range(2):
        i_ = int((i * 2 + j) / 5)
        j_ = (i * 2 + j) % 5

        axs[i, j].scatter(data_x, data_y , label='label', marker='o', s=20, facecolors='white', edgecolors=cm.Set2(0), alpha=0.3, zorder=1)
        axs[i, j].plot(start, end, label='label', color=cm.Set2(1), lw=1, zorder=0)
        axs[i, j].set_xlim([0, 1])
        axs[i, j].set_ylim([0, 1])
        axs[i, j].text(0.9, 0.1, title_list[i * 2 + j], fontdict=label_font, color='black', verticalalignment='center', horizontalalignment='center')

        if j == 0:
            axs[i, j].set_ylabel('y label', fontdict=label_font)
        if i == 4:
            axs[i, j].set_xlabel('x label', fontdict=label_font)

        # Setup the shape to a square
        axs[i, j].set_aspect('equal', adjustable='box')

        # Setup legend
        axs[i, j].legend(loc='upper left', prop=legend_font)

        # Setup background gray line
        axs[i, j].grid(axis='both', color='black', alpha=0.1)

        # Setup axis font family 
        axs[i, j].tick_params(axis='both', which='major', labelsize=14) 
        labels = axs[i, j].get_xticklabels() + axs[i, j].get_yticklabels()
        [label.set_fontname('serif') for label in labels]

# Save figure
plt.tight_layout()
plt.savefig('path', bbox_inches = 'tight')
