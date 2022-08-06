import matplotlib.pyplot as plt
from matplotlib import cm
plt.rcParams.update({'text.usetex': True})

# Font setup
title_font = {'family': 'Arial Black', 'fontsize': 18, 'fontweight': 'bold'}
label_font = {'color': 'blue', 'size': 14, 'family': 'serif'}

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
fig = plt.figure(figsize=(12, 10))
ax = fig.gca(projection='3d')

# Shape surf
surf = ax.plot_surface(x, y, z, cmap=cm.winter, linewidth=1, antialiased=True, alpha=0.3)

# Contour lines
contour = ax.contour(x, y, z, zdir='z', levels=8, offset=-0.5, cmap='winter', alpha=0.4)

# Point in the bottom
coll = ax.scatter(point_x, point_y, point_z, marker='o', color='red', alpha=0.4, s=10)
part = ax.scatter(point_x, point_y, point_z, marker='o', color='blue', alpha=0.4, s=10)

# Line in the bottom
ax.plot([start_x, start_y], [end_x, end_y], [-0.5, -0.5], color='blue', alpha=0.4, lw=1)

# Set value range
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_zlim(-0.5, 1)

# Set labels and title  
ax.set_title('title', fontdict=title_font)
ax.set_xlabel('x label', fontdict=label_font)
ax.set_ylabel('y label', fontdict=label_font)
ax.set_zlabel('z label', fontdict=label_font)

# Set label fontfamily
labels = ax.get_xticklabels() + ax.get_yticklabels() + ax.get_zticklabels()
[label.set_fontname('serif') for label in labels]

# Save figure
plt.tight_layout()
plt.savefig('path', bbox_inches='tight')
