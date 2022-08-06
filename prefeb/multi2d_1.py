import matplotlib.pyplot as plt
from matplotlib import cm
from itertools import product
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Palatino Linotype', 'fontsize': 34}
legend_font = {'family': 'Palatino Linotype', 'size': 32}
text_font = {'family': 'Palatino Linotype', 'fontsize': 14}

# Data
data = []
x = []
y = []

# Plot
fig, axs = plt.subplots(2, 4, figsize = (15, 8))

axs[0, 0].matshow(data, cmap='coolwarm', alpha=0.7)
axs[0, 0].scatter(x, y, label='point 1 label', marker='.', color='tomato')
axs[0, 0].scatter(x, y, label='point 2 label', marker='x', color='blue')

axs[0, 1].matshow(data, cmap = 'coolwarm', alpha=1)
axs[0, 2].matshow(data, cmap = 'coolwarm', alpha=1)
axs[0, 3].matshow(data, cmap = 'coolwarm', alpha=1)

axs[1, 0].matshow(data, cmap='coolwarm', alpha=0.7)
axs[1, 0].scatter(x, y, label='point 1 label', marker='.', color='tomato')
axs[1, 0].scatter(x, y, label='point 2 label', marker='x', color='blue')

axs[1, 1].matshow(data, cmap = 'coolwarm', alpha=1)
axs[1, 2].matshow(data, cmap = 'coolwarm', alpha=1)
im = axs[1, 3].matshow(data, cmap = 'coolwarm', alpha=1)

# Set title
axs[0, 0].set_title('title 1', fontdict=label_font)
axs[0, 1].set_title('title 2', fontdict=label_font)
axs[0, 2].set_title('title 3', fontdict=label_font)
axs[0, 3].set_title('title 4', fontdict=label_font)

# Set colorbar
fig.subplots_adjust(right=0.9)
position = fig.add_axes([1.01, 0.03, 0.02, 0.9]) # [left, down, right, up]
cb = fig.colorbar(im, cax=position)
cb.ax.tick_params(labelsize=28)

# Uncomment if use axis
# for i, j in product(range(2), range(4)):
#     axs[i, j].get_xaxis().set_visible(False)
#     axs[i, j].get_yaxis().set_visible(False)

# Set legend
handles, labels = axs[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', ncol=int(len(labels)), bbox_to_anchor=(0.5, -0.13), prop=legend_font)

plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
