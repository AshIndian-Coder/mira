"""
ROI and savings estimator for MIRA.

Estimates procurement and inventory savings from merging duplicate materials
into unified CNMCs. The savings come from:
  * Bulk purchasing discounts (larger order quantities)
  * Reduced inventory carrying costs (fewer SKUs)
  * Reduced procurement overhead (fewer suppliers to manage)

The estimator uses configurable assumptions from app.config.settings:
  * BULK_DISCOUNT_RATE: discount from consolidating orders
  * CARRYING_COST_RATE: annual inventory holding cost rate
  * SAFETY_STOCK_DAYS: safety stock days reduced per merged SKU
"""
