from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class JaniceBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class JaniceAppraisalDesignation(str, Enum):
    appraisal = "appraisal"
    wtb = "wtb"
    wts = "wts"


class JaniceAppraisalPricing(str, Enum):
    buy = "buy"
    split = "split"
    sell = "sell"
    purchase = "purchase"


class JaniceAppraisalPricingVariant(str, Enum):
    immediate = "immediate"
    top5percent = "top5percent"


class JanicePricerMarket(JaniceBaseModel):
    id: int
    name: str | None = None


class JaniceItemType(JaniceBaseModel):
    eid: int
    name: str | None = None
    volume: float
    packaged_volume: float = Field(alias="packagedVolume")


class JaniceAppraisalValues(JaniceBaseModel):
    total_buy_price: float = Field(alias="totalBuyPrice")
    total_split_price: float = Field(alias="totalSplitPrice")
    total_sell_price: float = Field(alias="totalSellPrice")


class JaniceAppraisalItemValues(JaniceBaseModel):
    buy_price: float = Field(alias="buyPrice")
    split_price: float = Field(alias="splitPrice")
    sell_price: float = Field(alias="sellPrice")
    buy_price_total: float = Field(alias="buyPriceTotal")
    split_price_total: float = Field(alias="splitPriceTotal")
    sell_price_total: float = Field(alias="sellPriceTotal")
    buy_price_5_day_median: float = Field(alias="buyPrice5DayMedian")
    split_price_5_day_median: float = Field(alias="splitPrice5DayMedian")
    sell_price_5_day_median: float = Field(alias="sellPrice5DayMedian")
    buy_price_30_day_median: float = Field(alias="buyPrice30DayMedian")
    split_price_30_day_median: float = Field(alias="splitPrice30DayMedian")
    sell_price_30_day_median: float = Field(alias="sellPrice30DayMedian")


class JaniceAppraisalItem(JaniceBaseModel):
    id: int
    amount: int
    buy_order_count: int = Field(alias="buyOrderCount")
    buy_volume: int = Field(alias="buyVolume")
    sell_order_count: int = Field(alias="sellOrderCount")
    sell_volume: int = Field(alias="sellVolume")
    effective_prices: JaniceAppraisalItemValues = Field(alias="effectivePrices")
    immediate_prices: JaniceAppraisalItemValues = Field(alias="immediatePrices")
    top5_average_prices: JaniceAppraisalItemValues = Field(alias="top5AveragePrices")
    total_volume: float = Field(alias="totalVolume")
    total_packaged_volume: float = Field(alias="totalPackagedVolume")
    item_type: JaniceItemType = Field(alias="itemType")


class JaniceAppraisal(JaniceBaseModel):
    id: int
    created: datetime
    expires: datetime
    dataset_time: datetime = Field(alias="datasetTime")
    code: str | None = None
    designation: JaniceAppraisalDesignation
    pricing: JaniceAppraisalPricing
    pricing_variant: JaniceAppraisalPricingVariant = Field(alias="pricingVariant")
    price_percentage: float = Field(alias="pricePercentage")
    comment: str | None = None
    is_compactized: bool = Field(alias="isCompactized")
    input: str | None = None
    failures: str | None = None
    market: JanicePricerMarket
    total_volume: float = Field(alias="totalVolume")
    total_packaged_volume: float = Field(alias="totalPackagedVolume")
    effective_prices: JaniceAppraisalValues = Field(alias="effectivePrices")
    immediate_prices: JaniceAppraisalValues = Field(alias="immediatePrices")
    top5_average_prices: JaniceAppraisalValues = Field(alias="top5AveragePrices")
    items: list[JaniceAppraisalItem] | None = None
