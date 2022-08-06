import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Setup font
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 14}

# Data
a = []
b = []
l = []
x = []
y = []

# Plot
fig, axs = plt.subplots(4, 4, figsize=(16, 16))

# Left bottom scatter plot
for i in range(1, 4):
    for j in range(i):
        axs[i, j].scatter(x, y, label='label1', marker='o', s=20, facecolors='white', edgecolors=cm.Set2(0), alpha=0.3, zorder=1)
        axs[i, j].plot(a, b, label='label2', color=cm.Set2(1), lw=1, zorder=0)
        axs[i, j].set_xlim([-1, 1])
        axs[i, j].set_ylim([-1, 1])
        if j == 0:
            axs[i, j].set_ylabel('Label', fontdict=label_font)
        if i == 3:
            axs[i, j].set_xlabel('Label', fontdict=label_font)

# Center hist plot
for i in range(4):
    n, bins, patchs = axs[i, i].hist(x, bins=16, density=True, range=(-4, 4), edgecolor='white', lw=1, )
    axs[i, i].plot(l, 1/np.sqrt(2*np.pi)*np.exp(-(l**2)/2), label='label', color=cm.Set2(1), lw=1)
    for j in range(len(patchs)):
        patchs[j].set_facecolor(cm.BuGn(j*int(255/20)))
    if i == 0:
       axs[i, i].set_ylabel('label', fontdict=label_font) 
    if i == 3:
       axs[i, i].set_xlabel('label', fontdict=label_font)

# Right upper value
for i in range(3):
    for j in range(i+1, 4):
        axs[i, j].scatter(x, y, label='label1', marker='o', s=20, facecolors='white', edgecolors=cm.Set2(0), alpha=0.3, zorder=1)
        axs[i, j].plot(a, b, label='label2', color=cm.Set2(1), lw=1, zorder=0)
        axs[i, j].set_xlim([-1, 1])
        axs[i, j].set_ylim([-1, 1])

# Figure setup
for i in range(4):
    for j in range(4):
        axs[i, j].legend(loc='upper left', prop=legend_font)
        axs[i, j].grid(axis='both', color='black', alpha=0.1)
        axs[i, j].tick_params(axis='both', which='major', labelsize=14) 
        labels = axs[i, j].get_xticklabels() + axs[i, j].get_yticklabels()
        [label.set_fontname('serif') for label in labels]

# Save figure
plt.tight_layout()
plt.savefig('path', bbox_inches = 'tight')
