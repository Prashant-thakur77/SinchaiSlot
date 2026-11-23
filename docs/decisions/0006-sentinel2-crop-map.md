# 0006 Sentinel-2 crop-calendar map

**Decision.** Crop type comes from a per-pixel 10 m NDVI time series over one agricultural year
(June 2024 to May 2025), built from Sentinel-2 L2A Collection 1 scenes on the keyless Earth Search
STAC catalogue, and classified by a transparent phenology rule set into season classes: kharif only
(mostly paddy), rabi only (wheat, maize, mustard), double cropped, orchard/trees, fallow/built-up,
water and other/mixed. Imagery is labelled REAL, classes DERIVED.

**Why rules, not a trained model.** No crop labels for this area are available offline, so a
supervised model could not be trained or tested honestly. The north Bihar calendar is regular: paddy
peaks in late August to early October, wheat in late January to February, with a bare trough in
November-December. A season-peak rule follows that calendar directly, every threshold is visible in
the code and the snapshot JSON, and anyone can check a pixel by looking at its series.

**Why Collection 1.** The older `sentinel-2-l2a` collection on the same catalogue declared a -0.1
reflectance offset in its metadata, but the stored values for this tile did not carry the matching
+1000 shift. Applying the declared offset produced negative red reflectance and NDVI near 1 over
town and water. Collection 1 stores values consistent with its metadata, and the pipeline now
stops if more than 5 % of clear pixels have negative red reflectance.

**Thresholds.** Crop canopy peak NDVI >= 0.60, no crop < 0.40, never green < 0.35 for the whole
year, trees when the year's 10th percentile >= 0.35 and median >= 0.55 (deciduous trees dip in
February-March), water when median NDWI > 0.05 and median NDVI < 0.1, double cropping needs an
inter-season trough at least 0.15 below the lower peak.

**Limits (published with the results).**
- Season classes, not species: paddy vs kharif maize, and wheat vs rabi maize, mustard, potato or
  lentil, cannot be told apart by NDVI timing alone.
- Fallow and built-up are one class.
- Monsoon cloud leaves 5 clear looks in the kharif peak window; a short-lived peak can be missed.
- Not validated against field labels. AgriFieldNet or a field visit would be needed for accuracy
  numbers.
- The configured site point is Samastipur town, so the current AOI is mostly urban (11.5 %
  cropland). The crop mix should be re-derived for the confirmed pilot cluster before it replaces
  the village assumption.
