# Deck assets: real CT slices (hero patient NLST 134503)

Exported Oct 25 from the Spark MD worker on the event GB10 (key axial slices rendered by the imaging pipeline, lung window).
`*_gray.png` = as rendered; `*_color.png` = the same image through a jet colormap (as in the UI's Color mode).

| File | What |
| --- | --- |
| `hero134503_T0_LLL_*` | Year 0 screen, LLL nodule (radiologist-confirmed mean 6.5 mm → Lung-RADS 3) |
| `hero134503_T0_RUL_secondary_*` | Year 0 screen, secondary RUL nodule (5.0 mm) |
| `hero134503_T1_LLL_*` | Year 1 screen (357 days later), same LLL nodule (10.4 mm, +3.9 mm → Lung-RADS 4B) |
| `hero134503_T0_vs_T1_*` | Side-by-side for the time-machine slide |

Sizes are radiologist-confirmed diameters from the demo (A7 proposals accepted unedited); categories are the Lung-RADS v2022 engine's output. Research demo, not for clinical use.

**Credit (required):** National Lung Screening Trial data via The Cancer Imaging Archive, CC BY 4.0, doi:10.7937/TCIA.HMQ8-J677 (accessed via NCI Imaging Data Commons, Fedorov et al. 2023).
