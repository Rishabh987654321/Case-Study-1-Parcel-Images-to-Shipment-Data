# Robustness evaluation (Phase 5 task 3)

Augmented copies of all 38 ground-truth images, one augmentation at a time (not stacked), run through the same pipeline (`backend/app/pipeline/cli.py`). Crop augmentation uses a fixed random seed (20261114) for reproducibility.

## Baseline (un-augmented, for comparison)

| Metric | Value |
| --- | --- |
| Wrong-extraction rate | 4.0% (1/25 predicted-OK) |
| AWB recall | 75.0% (of 32 truth-OK) |
| Silent-miss rate | 16.7% |
| Status counts | {'OK': 25, 'FLAGGED': 13} |

## Per-augmentation results

| Augmentation | Wrong-extraction rate | AWB recall | Silent-miss rate | Status counts |
| --- | --- | --- | --- | --- |
| rotate90 | 0.0% (0/12) | 37.5% | 0.0% | {'FLAGGED': 26, 'OK': 12} |
| rotate180 | 0.0% (0/11) | 34.4% | 0.0% | {'FLAGGED': 27, 'OK': 11} |
| downscale50 | 7.4% (2/27) | 78.1% | 33.3% | {'OK': 27, 'ERROR': 4, 'FLAGGED': 7} |
| blur5x5 | 4.0% (1/25) | 75.0% | 16.7% | {'OK': 25, 'FLAGGED': 13} |
| brightness_minus30 | 3.8% (1/26) | 78.1% | 16.7% | {'OK': 26, 'FLAGGED': 12} |
| brightness_plus30 | 4.0% (1/25) | 75.0% | 16.7% | {'OK': 25, 'FLAGGED': 13} |
| jpeg_q40 | 4.3% (1/23) | 68.8% | 16.7% | {'OK': 23, 'FLAGGED': 15} |
| crop_5_10pct | 20.0% (1/5) | 12.5% | 0.0% | {'FLAGGED': 33, 'OK': 5} |

## Interpretation

- **rotate90**: recall -37.5%, wrong-extraction -4.0% -> GOOD (recall dropped, wrong-extraction did not rise)
- **rotate180**: recall -40.6%, wrong-extraction -4.0% -> GOOD (recall dropped, wrong-extraction did not rise)
- **downscale50**: recall +3.1%, wrong-extraction +3.4% -> WATCH (wrong-extraction rate increased)
  - NEW wrong-extraction cases (not wrong at baseline): No Shipment packet captured_png.rf.1VvRtdnwIQAHs1Q83pHV.png
  - pre-existing wrong-extraction case, unaffected by this augmentation: Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png
- **blur5x5**: recall +0.0%, wrong-extraction +0.0% -> GOOD (recall dropped, wrong-extraction did not rise)
  - pre-existing wrong-extraction case, unaffected by this augmentation: Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png
- **brightness_minus30**: recall +3.1%, wrong-extraction -0.2% -> mixed
  - pre-existing wrong-extraction case, unaffected by this augmentation: Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png
- **brightness_plus30**: recall +0.0%, wrong-extraction +0.0% -> GOOD (recall dropped, wrong-extraction did not rise)
  - pre-existing wrong-extraction case, unaffected by this augmentation: Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png
- **jpeg_q40**: recall -6.2%, wrong-extraction +0.3% -> GOOD (recall dropped, wrong-extraction did not rise)
  - pre-existing wrong-extraction case, unaffected by this augmentation: Multiple shipment packets in single sorter images_png.rf.CItY4df8qqgsLt5AchtU.png
- **crop_5_10pct**: recall -62.5%, wrong-extraction +16.0% -> WATCH (wrong-extraction rate increased)
  - NEW wrong-extraction cases (not wrong at baseline): 12_jpeg.rf.wM6DblJOpOxpPMlir0BR.jpeg
