import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
label_font = {'family': 'Arial Black', 'fontsize': 26}
title_font = {'family': 'Arial Black', 'fontsize': 26, 'fontweight': 'bold'}

# Data
data_x = []
data_y = []
accelation = []

# Plot
fig, axs = plt.subplots(2, 6, figsize=(24, 8))
for i in range(2):
    for j in range(6):
            for idx, (m, n) in enumerate(zip(data_x, data_y)):
                axs[i, j].scatter(m, n, marker='o', alpha=1, color=cm.RdYlBu_r(accelation[idx]))

# Set value range
axs[0, 0].set_xlim([0.5, 5.5])
axs[0, 0].set_ylim([0.5, 4])
axs[1, 0].set_xlim([0.5, 5.5])
axs[1, 0].set_ylim([0.5, 4])

# Set axis off
axs[0, 0].set_xticks([])
axs[0, 0].set_yticks([])
axs[0, 0].set_yticklabels([])
axs[0, 0].set_xticklabels([])
axs[1, 0].set_xticks([])
axs[1, 0].set_yticks([])
axs[1, 0].set_yticklabels([])
axs[1, 0].set_xticklabels([])

# Set title and label
axs[0, 0].set_title('$t=0$', fontdict = title_font)
axs[0, 1].set_title('$t=1$', fontdict = title_font)
axs[0, 2].set_title('$t=2$', fontdict = title_font)
axs[0, 3].set_title('$t=3$', fontdict = title_font)
axs[0, 4].set_title('$t=4$', fontdict = title_font)
axs[0, 5].set_title('$t=5$', fontdict = title_font)
axs[0, 0].set_ylabel('y label 1', fontdict=label_font)
axs[1, 0].set_ylabel('y label 2', fontdict=label_font)

for i in range(1, 6):
    # Set value range
    axs[0, i].set_xlim([0.5, 5.5])
    axs[0, i].set_ylim([0.5, 4])
    axs[1, i].set_xlim([0.5, 5.5])
    axs[1, i].set_ylim([0.5, 4])

    # Set axis off
    axs[0, i].get_xaxis().set_visible(False)
    axs[0, i].get_yaxis().set_visible(False)
    axs[1, i].get_xaxis().set_visible(False)
    axs[1, i].get_yaxis().set_visible(False)

# Save figure
plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
