# Answer key: ship_design_spec.pdf

MV Nordic Aurora is a made-up ship. The document has 26 values:
10 wrong, 12 right and 4 that no rule in the project covers.
Every value is clearly inside or outside its limit, so rounding cannot change the answer.

A correct check shows the 10 wrong values as issues, boxed in red, and never marks a
right value or an uncovered value as an issue.

| Page | Element | Value | Expected | Why |
|---|---|---|---|---|
| 1 | Length overall | 92.4 m | Not checked (no rule) | no rule covers ship length |
| 1 | Fresh water tank | 45 m3 | Not checked (no rule) | no rule covers tank capacity |
| 1 | Main engines | 3200 kW | Not checked (no rule) | no rule covers engine power |
| 1 | Corridor 6-01 | 1100 mm | Right | at least 915 mm required (ADA 403.5.1) |
| 1 | Corridor 6-02 | 850 mm | Wrong (issue) | 65 mm below the 915 mm minimum |
| 1 | Accessible route to cabin 6112 | 950 mm | Right | at least 915 mm required |
| 1 | Cabin 6112 entrance door | 860 mm | Right | at least 815 mm required (ADA 404.2.3) |
| 1 | Public toilet 6-03 door | 780 mm | Wrong (issue) | 35 mm below the 815 mm minimum |
| 1 | Cabin 6112 door threshold | 10 mm | Right | at most 13 mm allowed (ADA 404.2.5) |
| 1 | Balcony door 6120 threshold | 22 mm | Wrong (issue) | 9 mm above the 13 mm maximum |
| 1 | Ramp to the pool deck | 1:14 | Right | 1:12 or flatter required (ADA 405.2) |
| 1 | Aft lobby ramp | 1:10 | Wrong (issue) | steeper than the 1:12 maximum |
| 1 | Main stair handrail | 900 mm | Right | 865 to 965 mm required (ADA 505.4) |
| 1 | Crew stair aft handrail | 1010 mm | Wrong (issue) | 45 mm above the 965 mm maximum |
| 2 | Cabin 6112 turning space | 1600 mm | Right | at least 1525 mm required (ADA 304.3.1) |
| 2 | Cabin 6112 toilet | 450 mm | Right | 430 to 485 mm required (ADA 604.4) |
| 2 | Cabin 6112 light switch | 1300 mm | Wrong (issue) | 80 mm above the 1220 mm maximum reach (ADA 308.2.1) |
| 2 | Public toilet 6-03 toilet | 400 mm | Wrong (issue) | 30 mm below the 430 mm minimum |
| 2 | Reception counter | 800 mm | Right | 710 to 865 mm required (ADA 902.3) |
| 2 | Aft lounge bar counter | 960 mm | Wrong (issue) | 95 mm above the 865 mm maximum |
| 2 | Superstructure door frame 52 | 460 mm | Right | at least 380 mm required (Load Lines reg. 12(3)) |
| 2 | Superstructure door frame 118 | 300 mm | Wrong (issue) | 80 mm below the 380 mm minimum |
| 2 | Sun deck guard rail | 1050 mm | Right | at least 1 m required (Load Lines reg. 25) |
| 2 | Mooring deck guard rail | 940 mm | Wrong (issue) | 60 mm below the 1 m minimum |
| 2 | Ballast water exchange | 96 % | Right | at least 95 % required (BWM D-1) |
| 2 | Hull bottom plating | 12 mm | Not checked (no rule) | no rule in the project covers plate thickness |

Make the document again with `python scripts/make_design_spec.py`.
