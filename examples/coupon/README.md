# PrintLoop test coupon

`coupon_p1s_pla.3mf`: a 60×20×2 mm plate, two 8×8×13 mm pillars and a 44 mm bridge on top (our own model, boxes only). In ~12 minutes on a P1S it shows bridges, stringing between the pillars, walls and the first layer.

Settings: BambuStudio system profiles `Bambu Lab P1S 0.4 nozzle`, `0.20mm Standard @BBL X1C`, `Bambu PLA Basic @BBL P1S 0.4 nozzle` (with `filament_density` set to 1.26, which is not inherited from the CLI). Plate: Cool Plate (from the system profile); if you print on another plate, change it in the slicer before generating the test set, or pass `printloop testset --bed "Textured PEI Plate"`.

Rebuild: `uv run printloop coupon`.
