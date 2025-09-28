#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 26 21:24:56 2025

@author: peterfelfer
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
from skimage import measure, morphology
from scipy.ndimage import median_filter

def detect_thinnest_section(img_path):
    """
    Detect the thinnest horizontal cross-section of a vertically oriented bar.
    Shows plots and returns info as dict.
    """
    # --- 1) Load grayscale
    I0 = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if I0 is None:
        raise ValueError(f"Could not read {img_path}")
    H, W = I0.shape

    # --- 2) Threshold (assume specimen dark on bright background)
    _, bw = cv2.threshold(I0, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.bitwise_not(bw)  # invert: specimen white
    bw = bw.astype(bool)

    # Keep largest connected component
    labels = measure.label(bw, connectivity=2)
    props = measure.regionprops(labels)
    if not props:
        raise ValueError("No specimen found")
    largest = max(props, key=lambda r: r.area).label
    BW = (labels == largest)
    BW = morphology.remove_small_holes(BW, area_threshold=64)

    # --- 3) Width profile row by row
    width_px = np.full(H, np.nan)
    xL = np.full(H, np.nan)
    xR = np.full(H, np.nan)
    for r in range(H):
        cols = np.where(BW[r, :])[0]
        if cols.size > 0:
            xL[r], xR[r] = cols[0], cols[-1]
            width_px[r] = xR[r] - xL[r] + 1

    # Smooth with median filter
    width_px_sm = median_filter(np.where(np.isfinite(width_px), width_px, np.inf), size=11)

    # --- 4) Find minimum width
    rMin = int(np.argmin(width_px_sm))
    x1, x2 = int(xL[rMin]), int(xR[rMin])
    min_width_px = float(width_px_sm[rMin])

    # --- 5) Plot results
    fig, axs = plt.subplots(1, 2, figsize=(12, 6))

    # A) Original image + outline + green line
    axs[0].imshow(I0, cmap='gray')
    contours = measure.find_contours(BW, 0.5)
    for contour in contours:
        axs[0].plot(contour[:, 1], contour[:, 0], color=(0.2, 0.8, 1), lw=1)  # cyan outline
    axs[0].plot([x1, x2], [rMin, rMin], 'g-', lw=4)
    axs[0].plot([x1, x2], [rMin, rMin], 'o', ms=8, mfc='g', mec='k', mew=1.5)
    axs[0].set_title(f"Min width = {min_width_px:.1f} px")
    axs[0].set_xlim(0, W)
    axs[0].set_ylim(H, 0)  # keep image coords

    # B) Width profile
    axs[1].plot(width_px, 'k:', label="Raw width")
    axs[1].plot(width_px_sm, 'b-', label="Smoothed")
    axs[1].axhline(min_width_px, color='g', lw=2, label="Min width")
    axs[1].axvline(rMin, color='g', ls='--', label="Min row")
    axs[1].set_xlabel("Row (y)")
    axs[1].set_ylabel("Width [px]")
    axs[1].set_title("Width profile")
    axs[1].legend()
    axs[1].grid(True)

    plt.tight_layout()
    plt.show()

    # --- 6) Return results
    return {
        "minWidthPx": min_width_px,
        "rowIdx": rMin,
        "line": (x1, rMin, x2, rMin),
        "mask": BW
    }

# ------------------------------
# Example usage in Spyder:
if __name__ == "__main__":
    img_path = "/Users/peterfelfer/Dropbox/Mac/Downloads/ChatGPT Image Sep 26, 2025, 03_37_35 PM.png"   # <- replace with your image path
    result = detect_thinnest_section(img_path)
    print(result)
