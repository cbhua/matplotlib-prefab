import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 18}

# Data
x1 = np.zeros([4, 100])
y1 = np.zeros([4, 100])
x2 = np.zeros([4, 100])
y2 = np.zeros([4, 100])

# Plot
fig, axs = plt.subplots(4, 1, figsize=(15, 10))
    
for idx in range(4):
    axs[idx].plot(x1[idx], y1[idx], label=f'label{idx}', color=cm.Set2(0), lw=1)
    axs[idx].plot(x2[idx], y2[idx], label=f'label{idx}', color=cm.Set2(1), lw=1)

    # axs[idx].set_title('title', fontdict=title_font) # Uncomment if titles are not shared
    # axs[idx].set_xlabel('xlabel', fontdict=label_font) # Uncomment if x label is not shared
    axs[idx].set_ylabel('ylabel', fontdict=label_font)

    # If customize ticks
    # xticks = []
    # yticks = []
    # axs[idx].set_xticks(xticks)
    # axs[idx].set_yticks(yticks)

    # If customize scale
    # axs[idx].set_xscale('linear')
    # axs[idx].set_yscale('linear')

    # If use sci notation
    # axs[0].ticklabel_format(style='sci', scilimits=(-1, 2), axis='x')
    # axs[0].ticklabel_format(style='sci', scilimits=(-1, 2), axis='y')

    axs[idx].legend(loc='upper left', prop=legend_font)
    axs[idx].grid(axis='both', color='black', alpha=0.1)
    axs[idx].tick_params(axis='both', which='major', labelsize=18) 

    # Set label fontfamily
    labels = axs[idx].get_xticklabels() + axs[idx].get_yticklabels()
    [label.set_fontname('serif') for label in labels]

# Comment if title or x label are not shared
axs[-1].set_xlabel('xlabel', fontdict=label_font)
axs[0].set_title('title', fontdict=label_font)

plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
