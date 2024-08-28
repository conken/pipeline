from astropy.io import fits
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy
import pickle
from photutils.aperture import RectangularAperture

from pywifes.wifes_utils import is_halfframe


def slitlet_cutout(image, aperture):
    mask = aperture.to_mask(method="center")
    cutout = mask.cutout(image)
    return cutout


def slitlet_aperture(boundaries, halfframe, bin_x=1, bin_y=2):
    xmin, xmax, ymin, ymax = boundaries
    xmin = numpy.round(xmin // bin_x)
    xmax = numpy.round(xmax // bin_x)

    if halfframe:
        ymin = numpy.round(ymin // bin_y) - (1028 // bin_y)
        ymax = numpy.round(ymax // bin_y) - (1028 // bin_y)
    else:
        ymin = numpy.round(ymin // bin_y)
        ymax = numpy.round(ymax // bin_y)

    center_x = (xmin + xmax) / 2
    center_y = (ymin + ymax) / 2
    width = xmax - xmin
    height = ymax - ymin
    aperture = RectangularAperture((center_x, center_y), width, height)
    return aperture


def read_pkl(path_pkl):
    with open(path_pkl, 'rb') as file:
        data = pickle.load(file)
    return data


def plot_slitlet(ax, path_slitlet, halfframe):

    if halfframe:
        first = 7
        last = 19
    else:
        first = 1
        last = 26

    slitlets = read_pkl(path_slitlet)
    # Toy plot for labeling
    ax.plot(0, 0, color='red', lw=1, ls='--', label='Slitlet boundary', zorder=-1)

    for index in range(first, last):
        slit_number = str(index)
        boundaries = slitlets[slit_number]
        aperture = slitlet_aperture(boundaries, halfframe, bin_x=1, bin_y=2)
        aperture.plot(ax=ax, color='red', lw=1, ls='--')


def plot_fits(ax, image_path, min=5, max=95, cmap="nipy_spectral"):
    data = fits.getdata(image_path)
    vmin, vmax = numpy.percentile(data, (min, max))
    img = ax.imshow(data, vmin=vmin, vmax=vmax, cmap=cmap, origin="lower", aspect='auto', interpolation='None')
    return img


def plot_collapsed_slitlets(ax, path_slitlet, image_path):
    image = fits.getdata(image_path)
    slitlets = read_pkl(path_slitlet)
    for slit_number in slitlets:
        boundaries = slitlets[slit_number]
        aperture = slitlet_aperture(boundaries, bin_x=1, bin_y=2)
        cutout = slitlet_cutout(image, aperture)
        median_slitlet = numpy.median(cutout, axis=0)
        ax.plot(median_slitlet)


def slitlet_yticks(path_slitlet, halfframe, bin_x=1, bin_y=2):
    slitlets = read_pkl(path_slitlet)
    y_centers = []
    slit_numbers = []

    if halfframe:
        first = 7
        last = 19
    else:
        first = 1
        last = 26

    for index in range(first, last):
        slit_number = str(index)
        boundaries = slitlets[slit_number]
        xmin, xmax, ymin, ymax = boundaries

        if halfframe:
            ymin = numpy.round(ymin // bin_y) - (1028 // bin_y)
            ymax = numpy.round(ymax // bin_y) - (1028 // bin_y)
        else:
            ymin = numpy.round(ymin // bin_y)
            ymax = numpy.round(ymax // bin_y)

        center_y = (ymin + ymax) / 2

        y_centers.append(center_y)
        slit_numbers.append(slit_number)
    return y_centers, slit_numbers


def flatfield_plot(flat_image_path, slitlet_path, title, output_plot):
    # Predefined list of colors (20 colors from 'viridis' colormap)
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#393b79', '#637939', '#8c6d31', '#843c39', '#7b4173',
        '#5254a3', '#6b6ecf', '#9c9ede', '#8ca252', '#b5cf6b',
        '#cedb9c', '#bd9e39', '#e7ba52', '#e7969c', '#de9ed6'
    ]
    # Create figure and subplots with shared x-axis and different heights
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10), sharex=True,
                                   gridspec_kw={'height_ratios': [1.5, 1]})

    # Plot Title
    plt.suptitle(title, size=20)

    # Plot slitlets over 2D flatfield on the top
    img = plot_fits(ax1, flat_image_path, cmap='viridis')
    x_limits = ax1.get_xlim()

    # Check if is half frame
    halfframe = is_halfframe(flat_image_path)

    if halfframe:
        first = 7
        last = 19
    else:
        first = 1
        last = 26

    plot_slitlet(ax1, slitlet_path, halfframe)
    ax1.label_outer()  # Hide x-tick labels for the top subplot

    # Add color bar to the top of ax1
    cbar = fig.colorbar(img, ax=ax1, orientation='horizontal', pad=0.01, location='top', fraction=0.05, aspect=50)
    cbar.set_label('Count [e$^{-1}$]', size=15)

    # Set yticks and labels for ax1
    y_centers, slit_numbers = slitlet_yticks(slitlet_path, halfframe, bin_x=1, bin_y=2)
    ax1.set_yticks(y_centers)
    ax1.set_yticklabels(slit_numbers)
    ax1.set_ylabel('Slitlet number', size=15)

    # Plot collapsed slitlet on the bottom
    slitlets = read_pkl(slitlet_path)

    for i, index in enumerate(range(first, last)):
        slit_number = str(index)
        color = colors[index % len(colors)]  # Use color from the list, cycle if more slitlets than colors
        boundaries = slitlets[slit_number]
        aperture = slitlet_aperture(boundaries, halfframe, bin_x=1, bin_y=2)
        cutout = slitlet_cutout(fits.getdata(flat_image_path), aperture)
        median_slitlet = numpy.median(cutout, axis=0)
        ax2.plot(median_slitlet, color=color)

        # Set the corresponding tick label color in ax1
        tick_labels = ax1.get_yticklabels()
        tick_labels[i].set_color(color)
        ax1.set_yticklabels(tick_labels, size=12)

    ax2.set_ylabel('Count [e$^{-1}$]', size=15)

    y2_limits = ax2.get_ylim()

    ax1.legend(loc='upper right', framealpha=1.0)

    # Ensure the x-limits of the 2D image are preserved
    ax1.set_xlim(x_limits)
    ax2.set_xlim(x_limits)
    ax2.set_ylim(y2_limits)

    ax2.set_xlabel('X-axis [pixel]', size=15)

    # Adjust layout and show the plot
    plt.savefig(output_plot, dpi=300)

    plt.close('all')


def final_wsol_plot(title, allx, ally, allarcs, resid, plot_path=None):
    fig = plt.figure(figsize=(10, 6))
    plt.suptitle(title)

    # Define GridSpec (3 rows 2 columns)
    gs = gridspec.GridSpec(3, 3, width_ratios=[3, 1, 0.5])  # Add width_ratios for the columns

    ax_left_top = fig.add_subplot(gs[0:2, 0:1])  # Subplot in the left column
    ax_left_top.plot(allx, ally, 'r.', markeredgecolor='w', markeredgewidth=0.2)
    ax_left_top.set_xlabel("X-axis [pixel]")
    ax_left_top.set_ylabel("Y-axis [pixel]")
    ax_left_top.grid(True)

    ax_left_bottom = fig.add_subplot(gs[2:, 0:2])  # Bottom subplot in the left column
    ax_left_bottom.plot(allarcs, resid, 'r.', markeredgecolor='w', markeredgewidth=0.2)
    ax_left_bottom.set_xlabel(r'Wavelength [$\AA$]')
    ax_left_bottom.set_ylabel(r'Residuals [$\AA$]')
    ax_left_bottom.yaxis.set_label_position("left")
    ax_left_bottom.yaxis.tick_left()
    ax_left_bottom.grid(True)

    # Create histogram of resid on the right side
    # Can use sharey to share y-axis with ax_bottom
    ax_hist = fig.add_subplot(gs[2, 2])  # sharey=ax_left_bottom)
    ax_hist.hist(resid, orientation='vertical', bins=40, color='red', density=True)
    ax_hist.yaxis.set_label_position("right")
    ax_hist.label_outer()

    # Compute mean and standard deviation of resid
    mean_resid = numpy.mean(resid)
    std_resid = numpy.std(resid)

    # Plotting the 3-sigma marks
    sigma_pos = mean_resid + std_resid
    sigma_neg = mean_resid - std_resid

    # Horizontal lines at +/-1 sigma
    ax_hist.axvline(sigma_pos, color='black', lw=0.8, linestyle='--', label=fr'$\sigma$: {std_resid:.2f} $\AA$')
    ax_hist.axvline(sigma_neg, color='black', lw=0.8, linestyle='--')

    ax_hist.legend(bbox_to_anchor=(0.5, -0.3), loc='center', framealpha=1.0, handlelength=1.2, frameon=False)
    ax_hist.grid(True)
    ax_hist.set_yticklabels([])
    ax_hist.set_yticks([])

    ax_top = fig.add_subplot(gs[0, 1:])  # Top subplot in the right column
    ax_top.plot(allx, resid, 'r.', markeredgecolor='w', markeredgewidth=0.2)
    ax_top.set_xlabel("X-axis [pixel]")
    ax_top.set_ylabel(r"Residuals [$\AA$]")
    ax_top.yaxis.set_label_position("right")
    ax_top.yaxis.tick_right()
    ax_top.grid(True)

    ax_middle = fig.add_subplot(gs[1, 1:])  # Middle subplot in the right column
    ax_middle.plot(resid, ally, 'r.', markeredgecolor='w', markeredgewidth=0.2)
    ax_middle.set_xlabel(r"Residuals [$\AA$]")
    ax_middle.set_ylabel("Y-axis [pixel]")
    ax_middle.yaxis.set_label_position("right")
    ax_middle.yaxis.tick_right()
    ax_middle.grid(True)

    plt.subplots_adjust(top=0.9, wspace=0.05, hspace=0.6, left=0.065, right=0.935, bottom=0.09)  # Adjust top to make room for suptitle

    plt.savefig(plot_path, dpi=300)
    plt.close('all')
