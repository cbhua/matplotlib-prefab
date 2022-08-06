import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams['figure.figsize'] = 26, 12
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'family': 'Arial Black', 'fontsize': 18}
legend_font = {'family': 'Palatino Linotype', 'size': 22}
text_font = {'family': 'Palatino Linotype', 'fontsize': 14}

# Data
x = []
y = []
z = []
point_x = []
point_y = []
point_z = []
start_x = []
start_y = []
end_x = []
end_y = []

# Plot
fig = plt.figure()
axs1 = fig.add_subplot(221, projection='3d')
axs2 = fig.add_subplot(211, projection='3d')

# Figure 1
# Shape surf
surf = axs1.plot_surface(x, y, z, label='surf label', cmap=cm.winter, linewidth=1, antialiased=True, alpha=0.3)

# Contour lines
contour = axs1.contour(x, y, z, zdir='z', levels=8, offset=-0.7, cmap='winter', alpha=0.4)

# Set value range
axs1.set_xlim(0, 1)
axs1.set_ylim(0, 1)
axs1.set_zlim(-0.7, 0.6)

# Set labels and title  
axs1.set_title('title', fontdict=title_font)
axs1.set_xlabel('x label', fontdict=label_font)
axs1.set_ylabel('y label', fontdict=label_font)
axs1.set_zlabel('z label', fontdict=label_font)

# Set the axis line to white
axs1.w_xaxis.line.set_color('white')
axs1.w_yaxis.line.set_color('white')
axs1.w_zaxis.line.set_color('white')

# Set the axis line to white
axs1.tick_params(axis='x', color='white')
axs1.tick_params(axis='y', color='white')
axs1.tick_params(axis='z', color='white')

# Decrease the mesh line color
surf._facecolors2d = surf._facecolor3d
surf._edgecolors2d = surf._edgecolor3d

# Set label fontfamily
labels = axs1.get_xticklabels() + axs1.get_yticklabels() + axs1.get_zticklabels()
[label.set_fontname('serif') for label in labels]

# Figure 2
# Shape surf
surf = axs2.plot_surface(x, y, z, cmap=cm.coolwarm, linewidth=1, antialiased=False, alpha=0.4)

# Contour lines
contour = axs2.contour(x, y, z, zdir='z', levels=8, offset=-0.7, cmap='winter', alpha=0.4)

# Point in the bottom
coll = axs2.scatter(point_x, point_y, point_z, label='point label1', marker='o', color='red', alpha=0.3, s=8)
part = axs2.scatter(point_x, point_y, point_z, label='point label2', marker='o', color='blue', alpha=0.4, s=10)

# Set value range
axs2.set_xlim(0, 1)
axs2.set_ylim(0, 1)
axs2.set_zlim(-0.7, 0.6)

# Set labels and title  
axs2.set_title('title', fontdict=title_font)
axs2.set_xlabel('X', fontdict=label_font)
axs2.set_ylabel('Y', fontdict=label_font)
axs2.set_zlabel('Z', fontdict=label_font)

# Set the axis line to white
axs2.w_xaxis.line.set_color('white')
axs2.w_yaxis.line.set_color('white')
axs2.w_zaxis.line.set_color('white')

# Set the axis line to white
axs2.tick_params(axis='x', color='white')
axs2.tick_params(axis='y', color='white')
axs2.tick_params(axis='z', color='white')

# Decrease the mesh line color
surf._facecolors2d = surf._facecolor3d
surf._edgecolors2d = surf._edgecolor3d

# Set label fontfamily
labels = axs2.get_xticklabels() + axs2.get_yticklabels() + axs2.get_zticklabels()
[label.set_fontname('serif') for label in labels]

# Set legend
handles, labels = axs2.get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', ncol=int(len(labels)/1), bbox_to_anchor=(0.38, 0.45), prop=legend_font, shadow=True, fancybox=True)

# Save figure
plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
