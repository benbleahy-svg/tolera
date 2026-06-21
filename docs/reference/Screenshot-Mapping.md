# Bid Factory — Screenshot Mapping Log

Maps each **canonical screenshot name** referenced in the Build Spec's Screenshot Index to the **actual source file** it was matched from. Matched files have been **copied** (originals preserved) into `Screenshots/Demo<X>/` under the canonical name, so the spec's image links resolve.

- **Source of actual files:** `~/BidFactory/Screenshots/<video-title>/`
- **Destination:** `~/Documents/Claude/Projects/Bid Factory/Screenshots/Demo<X>/`
- **Matching method:** every source image was opened and matched by visible content to the spec's "Shows" description. Confidence is noted per row.

## Summary

| | Canonical names in manifest | Placed | Unfilled |
|---|---|---|---|
| Demos D–N (video folders) | 111 | **100** | 11 |
| Demo C (recent Desktop screenshots) | 13 | **9** | 4 |
| Demo A (captured from YouTube demo) | 15 | **13** | 2 |
| Demo B (captured from YouTube demo) | 18 | **17** | 1 |
| **Total** | **157** | **139** | **18** |

Of the **37 images shown inline** in the spec body, **34 now render** (all inline figures of D, E, F, G, N; 3 of Demo C's 4; 5 of Demo A's 6; and 8 of Demo B's 9). The remaining **3** are `DemoA/16_build_order`, `DemoC/11_quote_level_summary_view`, and `DemoB/01_dashboard_workflows_notifications` (the home dashboard, which the Arch demo never opens — it goes straight to the quotes list).

## ✅ Demo A & Demo B filled from their YouTube demos

**Demo A was captured** (13 of 15) from the YouTube video *"Demo with a Customer: Precision Cut Industries + Global Shop Solutions ERP"* (youtu.be/a7GAEwIYjiU). Frames were grabbed at full 1920×1080 from the first ~33 minutes (per instruction). The 2 unfilled names — `16_build_order` and `17_shipping_payment` — are the checkout flow, which falls outside the reviewed window. See the Demo A table below. (Note: `06_line_item_part_estimating_view` was captured from part **253000PPA**'s estimating view, since the assembly **003-00102-001** named in the spec opens directly into the BOM Builder rather than a standard part page; the layout matches. `13` shows the assembly BOM + DB Roberts purchased components but not the Bulk-Edit modal, which the demo didn't display.)

**Demo C was filled** (9 of 13) from recent Desktop screenshots — the 2026-06-12, 10:16–10:18 PM Requirements Review batch (Blood Orange Machine, Hank Portney).

**Demo B was captured** (17 of 18) from the YouTube video *"Demo with a Customer: ARCH Medical Solutions"* (youtu.be/2s9Iyb-b-ek), Quote #15217 / account "CC's CNC Machining". Frames were grabbed at full 1920×1080 across the whole demo. The 1 unfilled name — `01_dashboard_workflows_notifications` — is the home Dashboard, which this demo never opens (after the intro slides it goes straight to the "My quotes" list). See the Demo B table below.

## Source folder → Demo mapping

| Demo | Spec title | Source folder |
|---|---|---|
| A | Precision Cut Industries + Global Shop ERP | YouTube: *Demo with a Customer…* (youtu.be/a7GAEwIYjiU), frames captured |
| B | Arch Medial Solutions | YouTube: *Demo with a Customer: ARCH Medical Solutions* (youtu.be/2s9Iyb-b-ek), frames captured |
| C | Requirements Review | recent Desktop screenshots (2026-06-12, 10:16–10:18 PM) |
| D | Meet the BOM Builder | `BOM Builder` |
| E | Custom Markups & Margins (PL #31) | `Custom Markups & Margins ` + `Pricing and Margin` |
| F | Free Part Viewer / Collaboration / Sourcing (PL #2) | `Power Lunch Ep 2` |
| G | Costing Templates (Processes) | `How to Cost Parts More Easily & Consistently` |
| H | 2025 Hidden Gems (PL #37) | `Power Lunch Ep 37` |
| I | Sheet Metal Fabricators (overview) | `PP for Sheet Metal Fab` |
| J | Nesting Deep-Dive | `Nest Parts within your Quoting Software` |
| K | CNC Machine Shops (overview) | `PP for CNC` |
| L | Purchased Components (real-time) | `Visability into Purchased Components` |
| M | Assembly Table Updates (PL #19) | `Power Lunch 19` |
| N | Geometric Feature Overview | `Geometry Viewer` |

---

## Per-demo mapping

> "Source file" names are from the original video folders. Note: `Geometry Viewer` and `Pricing and Margin` files use a non-breaking space before AM/PM in the real filename.

### Demo A — Precision Cut + Global Shop ERP (captured from YouTube)  *(13/15)*

> Source = youtu.be/a7GAEwIYjiU. Each frame captured at full 1920×1080 at the video timestamp shown.

| Canonical name | Video timestamp | Notes |
|---|---|---|
| 03_paperless_parts_main_dashboard.png | 8:26 | Workflows queue + Notifications panel |
| 04_quote_detail_page_files_notes.png | 11:05 | Quote #14801: line items, Quote Files, Internal/Customer notes |
| 05_quote_account_context_expedite_pricing.png | 9:36 | DTMA account ($83M/$151M revenue) + Expedite Pricing |
| 06_line_item_part_estimating_view.png | 28:11 | Part-estimating view (shown for 253000PPA; see note above) |
| 07_bom_builder_hierarchical_parts.png | 16:51 | BOM Builder, 47/1000 unique parts |
| 8_sheet_metal_part_interrogation_operations.png | 19:41 | Part 33000: interrogation + full operations breakdown |
| 09_pdf_drawing_viewer_ai_review_items.png | 22:01 | Part 33000 drawing + AI Review Items (Powder Coat, Deburr) |
| 10_multi_quantity_pricing_with_ai_review_flags.png | 23:41 | PP-08470001: 100/500/1000 pricing + Anodize/Deburr/AMS-4016 flags |
| 11_sheet_metal_nesting_module_configuration.png | 31:54 | Multi-component nesting config dialog (96×48 stock, ERP, settings) |
| 12_nesting_overview_sheet_metal_components.png | 31:40 | Nesting Overview grouping the sheet-metal components |
| 13_bulk_edit_components_assembly_bom_view.png | 29:01 | 253000PPA assembly BOM: sub/mfg/purchased + DB Roberts badges |
| 14_costing_pricing_summary_multi_quantity.png | 31:24 | Multi-qty cost rollup + Pricing (DTMA Markup 10%, margins 25%) |
| 15_quote_general_fields_workflow_status.png | 32:22 | Quote General + Workflows ("7 Incomplete Quote Items") |
| **16_build_order.png** | — | UNFILLED — checkout flow, after the 33-min review window |
| **17_shipping_payment.png** | — | UNFILLED — checkout flow, after the 33-min review window |

### Demo B — Arch Medial Solutions (captured from YouTube)  *(17/18)*

> Source = youtu.be/2s9Iyb-b-ek (*Demo with a Customer: ARCH Medical Solutions*). Quote #15217, account "CC's CNC Machining". Each frame captured at full 1920×1080 at the video timestamp shown.

| Canonical name | Video timestamp | Notes |
|---|---|---|
| **01_dashboard_workflows_notifications.png** | — | UNFILLED — home Dashboard never opened; demo goes straight from intro slides to the "My quotes" list |
| 02_quotes_list_sidebar_views.png | 6:05 | "My quotes" grid + saved-view sidebar (Due This Week, In-Progress, Outstanding, Workflow: Material Pricing / Ready for Executive Review) + status columns |
| 03_quote_detail_workflow_tracker.png | 7:00 | Quote #15217: General, Workflows tracker (RFQ Received → Quote Started → Outstanding Work → Quote Sent), People, Account, Expedite Pricing |
| 04_bulk_create_line_items_modal.png | 10:00 | Bulk Create Line Items modal — 7 parts auto-filled from the RFQ email with quantities |
| 05_quote_line_items_file_structure.png | 10:50 | Line-item sidebar + Quote Files (RFQ / Vendor Quotes / Supporting Files) |
| 06_review_items_auto_detected.png | 26:39 | OFFSET CONNECTOR drawing + auto-detected Review Items (Anodize, MIL-A-8625, Pack separately) |
| 07_assembly_bom_child_bom.png | 15:50 | PP-18932 Slap Hammer assembly — 6 manufactured components (Child BOM) |
| 08_line_item_part_detail_geometry_status.png | 16:10 | Part 3601215 OFFSET CONNECTOR: geometry (6.000×3.664×1.750, 11.924 cu.in) + Status & Workflow Steps |
| 09_part_library_match_categories.png | 16:50 | Part Library "2526 Matching Parts" — Exact File / Geometric / Name / Part# / Similar match buckets |
| 10_cad_viewer_part_setup_panel.png | 19:10 | 3D CAD viewer + Part Setup panel (part info, dimensions, CNC \| Milling, material) |
| 11_cad_viewer_face_annotation_team_chat.png | 20:50 | Face selected + TEAM chat annotation "@Chris Storro Can we do this face" |
| 12_geometric_features_milling_analysis.png | 21:30 | Geometric Features: Milling Features + 79 Milling Warnings (color-coded) |
| 13_feature_highlighting_on_3d_model.png | 23:40 | Deep-hole features highlighted (yellow) on the transparent 3D model |
| 14_create_rule_dialog_with_pdf.png | 25:40 | Create Rule dialog over the PDF (signal: GD&T / Datum ref count > 2; resolution: Inspection; assignee Courtney Camarillo) |
| 15_operations_costing_per_quantity.png | 27:07 | Operations (Saw, Mill Programming, Mill, Deburr, Inspection, Shipping Prep) + Operation Summary per qty 1/5/20 ($771.25 / $814.58 / $977.08) |
| 16_costing_pricing_breakdown_margins.png | 28:10 | Costing rollup + Pricing (CC's CNC Markup 20%, Material Margin 30%, General Margin 35%) |
| 18_addons_dropdown_options.png | 30:19 | Add-On dropdown open (Cert of Conformance, NRE, Tooling Charge, Special Packaging, FAI) |
| 17_addons_fai_lead_times.png | 30:40 | FAI add-on ($100), totals with add-ons, per-qty Lead Times (6 days) |

### Demo C — Requirements Review (recent Desktop screenshots)  *(9/13)*

> Source = the 2026-06-12 10:16–10:18 PM capture batch (originals are `Screenshot 2026-06-12 at 10.xx.xx PM.png` on the Desktop).

| Canonical name | Source file (Desktop) | Conf. |
|---|---|---|
| 01_quote_detail_part_setup.png | Screenshot…10.17.02 PM.png | high |
| 02_print_viewer_partsetup_panel.png | Screenshot…10.17.22 PM.png | high |
| 03_callout_popover.png | Screenshot…10.17.26 PM.png | high |
| 04_whiteout_mode.png | Screenshot…10.17.23 PM.png | medium |
| 06_create_rule_dialog_empty.png | Screenshot…10.17.39 PM.png | medium |
| 07_create_rule_with_filter_and_resolution.png | Screenshot…10.18.10 PM.png | high |
| 08_resolution_options_dropdown.png | Screenshot…10.18.00 PM.png | high |
| 09_signal_selector_tree.png | Screenshot…10.17.29 PM.png | high |
| 10_requirements_review_lineitem_panel.png | Screenshot…10.18.48 PM.png | high |
| **05_add_missing_extraction_modal.png** | — UNFILLED (not in batch) | — |
| **11_quote_level_summary_view.png** | — UNFILLED (not in batch) | — |
| **12_lineitem_process_section.png** | — UNFILLED (not in batch) | — |
| **13_operations_router_pricing_table.png** | — UNFILLED (not in batch) | — |

### Demo D — BOM Builder  *(10/11)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 02_pdf_viewer_assembly_drawing.png | download (19).png | high |
| 03_quote_detail_actions_dropdown.png | download (1).png | high |
| 04_split_pdf_toast_processing.png | download (2).png | high |
| 05_split_pdf_toast_success.png | download (3).png | high |
| 06_quote_files_after_split_wingman_tooltip.png | download (4).png | high |
| 07_bom_builder_modal_initial_loaded.png | download (9).png | high |
| 08_bom_builder_add_files_after.png | download (10).png | high |
| 09_bom_builder_subassemblies_expanded_level2.png | download (12).png | high |
| 11_bom_builder_complete_43_parts.png | download (14).png | medium |
| 12_published_bom_line_item_view.png | download (16).png | high |
| **10_bom_builder_subassemblies_level3.png** | — UNFILLED (no level-3 / X.Y.Z frame found) | — |

### Demo E — Custom Markups & Margins  *(14/16)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 03_pricing_today_slide.png | [Custom Markups] download.png | high |
| 04_custom_markups_overview_slide.png | [Custom Markups] download (1).png | high |
| 05_p3l_how_it_works_slide.png | [Custom Markups] download (2).png | high |
| 06_demo_quote_overview.png | [Custom Markups] download (3).png | high |
| 07_example1_difficult_material_costing_pricing.png | [Pricing and Margin] Screenshot…6.32.56 AM.png | high |
| 08_example2_laser_workcenter_costing_pricing.png | [Pricing and Margin] Screenshot…6.34.02 AM.png | high |
| 09_example3_labor_overhead_costing_pricing.png | [Pricing and Margin] Screenshot…6.35.26 AM.png | high |
| 11_example4_piece_price_tool_costing_pricing.png | [Pricing and Margin] Screenshot…6.36.00 AM.png | high |
| 12_example5_outside_finishes_costing_pricing.png | [Pricing and Margin] Screenshot…6.37.00 AM.png | high |
| 13_example6_complexity_operations_table.png | [Custom Markups] download (11).png | high |
| 14_example6_complexity_level3_pricing.png | [Custom Markups] download (12).png | medium |
| 15_example6_complexity_level2_pricing.png | [Pricing and Margin] Screenshot…6.39.28 AM.png | high |
| 16_quote_actions_dropdown_excel.png | [Custom Markups] download (21).png | high |
| 16_configure_pricing_processes.png | [Custom Markups] download (17).png | high |
| **17_excel_export_1.png** | — UNFILLED (exported Excel sheet never shown on screen) | — |
| **18_excel_export_2.png** | — UNFILLED (same) | — |

### Demo F — Power Lunch Ep 2  *(7/7)*

| Canonical name | Source file | Conf. |
|---|---|---|
| ep2_01_parts-library_0012.png | download (51).png | high |
| ep2_02_part-viewer_0121.png | download (1).png | high |
| ep2_03_geometric-analysis_0341.png | download (5).png | high |
| ep2_04_team-techmate_0544.png | download (9).png | high |
| ep2_05_pdf-annotate_1029.png | download (12).png | high |
| ep2_06_pemconnect_1557.png | download (17).png | high |
| ep2_07_files-tab_1956.png | download (18).png | high |

### Demo G — How to Cost Parts…  *(7/7)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 01_quote-detail_process-dropdown_~0016.png | download.png | high |
| 02_quote-detail_routing-generated_~0022.png | download (1).png | high |
| 03_process-config_general_~0046.png | download (3).png | high |
| 04_process-config_edit-operations-modal_~0060.png | download (4).png | high |
| 05_process-config_operations-list_~0074.png | download (5).png | high |
| 06_process-config_edit-pricing-items_~0081.png | download (6).png | high |
| 07_process-config_pricing-formula-editor_~0100.png | download (8).png | high |

### Demo H — Power Lunch Ep 37  *(11/13)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 01_quote_files_dxf.png | download.png | high |
| 02_bulk_update_thickness_modal.png | download (12).png | med-high |
| 03_operation_editor_variables.png | download (15).png | medium |
| 04_router_operations_costing.png | download (17).png | medium |
| 05_cnc_milling_operation_modal.png | download (4).png | high |
| 06_edit_dimensions_dialog.png | download (5).png | high |
| 07_part_setup_click_to_set.png | download (24).png | medium |
| 08_settings_email_templates.png | download (25).png | high |
| 09_settings_quote_display.png | download (26).png | high |
| 10_settings_units_date_security.png | download (27).png | high |
| 12_facilitate_order_drawer.png | download (10).png | medium |
| **11_digital_quote_expired.png** | — UNFILLED | — |
| **13_settings_facilitate_order_optin.png** | — UNFILLED | — |

### Demo I — PP for Sheet Metal Fab  *(11/12)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 02_quotes_list_saved_views.png | download.png | high |
| 03_bulk_create_line_items.png | download (2).png | high |
| 04_bom_builder_beta.png | download (3).png | medium |
| 05_print_requirements.png | download (4).png | medium |
| 06_cad_sheetmetal_warnings.png | download (6).png | high |
| 07_routing_costing.png | download (9).png | high |
| 08_nesting_overview.png | download (10).png | high |
| 09_pricing_markups.png | download (12).png | high |
| 10_quote_header_workflow.png | download (16).png | high |
| 11_email_template_send.png | download (18).png | high |
| 12_customer_digital_quote.png | download (19).png | high |
| **01_rfq_email.png** | — UNFILLED (no inbound RFQ-email shot) | — |

### Demo J — Nest Parts…  *(8/8)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 01_line_item_detail.png | download (11).png | medium |
| 02_update_process_material.png | download (1).png | high |
| 03_sheet_metal_interrogation.png | download (4).png | medium |
| 04_nesting_module_single.png | download (7).png | high |
| 05_nest_generated_metrics.png | download (9).png | medium |
| 06_multicomponent_overview.png | download (15).png | medium |
| 07_prepare_sheet_nests.png | download (18).png | high |
| 08_nest_result_object.png | download (21).png | high |

### Demo K — PP for CNC  *(7/12)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 06_requirements_review.png | download (2).png | high |
| 07_cad_viewer_warnings.png | download.png | high |
| 08_chat_panel.png | download (1).png | high |
| 09_update_process_material.png | download (3).png | high |
| 10_costing_pricing_tables.png | download (5).png | medium |
| 11_quote_account_expedite.png | download (7).png | medium |
| 12_send_email_template.png | download (8).png | high |
| **02_gmail_rfq_email.png** | — UNFILLED | — |
| **03_bulk_create_line_items.png** | — UNFILLED | — |
| **04_quotes_list_savedviews.png** | — UNFILLED | — |
| **05_print_viewer_part_setup.png** | — UNFILLED | — |
| **13_customer_digital_quote.png** | — UNFILLED | — |

### Demo L — Visability into Purchased Components  *(5/5)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 02_bom_component_context_menu.png | download.png | high |
| 03_convert_to_purchased_smart_match.png | download (1).png | high |
| 04_bom_purchased_pricing_inventory.png | download (3).png | high |
| 05_inventory_at_risk_high_volume.png | download (12).png | high |
| 07_realtime_pricing_settings_beta.png | download (10).png | high |

### Demo M — Power Lunch 19  *(7/7)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 04_ungrouped_drag_drop_reorder.png | download (1).png | high |
| 06_breadcrumb_sibling_dropdown.png | download (3).png | high |
| 07_unique_url_child.png | download (4).png | high |
| 09_thumbnail_hover_tooltip.png | download (6).png | high |
| 14_flat_bom_warnings_suppliers.png | download (11).png | high |
| 15_bulk_update_components_modal.png | download (12).png | high |
| 17_copy_pricing_panel.png | download (14).png | high |

### Demo N — Geometry Viewer  *(13/13)*

| Canonical name | Source file | Conf. |
|---|---|---|
| 01_title_no-cad-license.png | Screenshot…9.58.54 PM.png | high |
| 02_milling_features_warnings.png | Screenshot…9.58.58 PM.png | high |
| 03_milling_warnings_highlighted.png | Screenshot…9.59.00 PM.png | high |
| 04_lathe_features_live-tooling.png | Screenshot…9.59.05 PM.png | high |
| 05_lathe_bounding_box.png | Screenshot…9.59.07 PM.png | high |
| 06_sheetmetal_bends_kfactor.png | Screenshot…9.59.09 PM.png | high |
| 07_sheetmetal_unfolded_flatten.png | Screenshot…9.59.12 PM.png | high |
| 08_wire-edm_features_warnings.png | Screenshot…9.59.15 PM.png | high |
| 09_wire-edm_incompatible_faces.png | Screenshot…9.59.17 PM.png | high |
| 10_additive_stl_orientation.png | Screenshot…9.59.21 PM.png | high |
| 11_additive_reoriented.png | Screenshot…9.59.24 PM.png | medium |
| 12_waterjet-laser_dxf_flat.png | Screenshot…9.59.27 PM.png | high |
| 13_waterjet-laser_tight-corner.png | Screenshot…9.59.29 PM.png | high |

---

## Notes & follow-ups

- **Lower-confidence rows to spot-check:** C-04/06, D-11, E-14, H-02/03/04/07/12, I-04/05, J-01/03/05/06, K-10/11, N-11. Each note explains why; alternates exist in the source folders if a swap is needed.
- **Demos A & B** still need their source screenshots located before those 33 names (incl. 15 inline figures) can be filled. Demo C's 4 remaining names (`05`, `11`, `12`, `13`) weren't in the recent capture batch.
- A throwaway `Screenshots/_tmp_crops/` folder was created during matching and can be deleted manually.
