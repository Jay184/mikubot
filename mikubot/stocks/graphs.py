from datetime import datetime, timezone
from types import EllipsisType
from matplotlib import dates
from matplotlib.pyplot import subplots, Figure, Axes
from pandas import DataFrame, date_range, concat
import math

from .models import Security, Portfolio
from .history import HistoryService
from .intervals import IntervalData, SecurityIntervals, DayIntervalData, WeekIntervalData, MonthIntervalData


GraphDataItem = tuple[datetime, float]
GraphData = list[GraphDataItem]


class GraphService:
    def __init__(self, history: HistoryService):
        self.history = history

    @staticmethod
    def interval_data_for(interval: SecurityIntervals) -> IntervalData:
        interval_classes = {
            SecurityIntervals.day: DayIntervalData,
            SecurityIntervals.week: WeekIntervalData,
            SecurityIntervals.month: MonthIntervalData,
        }
        now = datetime.now(timezone.utc)
        return interval_classes[interval.value](now)

    def create_price_matrix(self, securities: list[Security], interval: SecurityIntervals, *, cols: int | EllipsisType = 3, fig_width: int = 6, fig_height: int = 3) -> tuple[Figure, list[Axes]]:
        interval_data = self.interval_data_for(interval)

        cols = self._get_optimal_cols(len(securities)) if cols is Ellipsis else cols

        # Gather graph data for each security
        data_list = [
            self.get_price_graph_data(sec.config.key, interval_data)
            for sec in securities
        ]

        # Create subplots
        fig, axes = self.create_graph_matrix(*data_list, interval=interval_data, cols=cols, fig_width=fig_width, fig_height=fig_height)

        # Annotate % change in title
        for ax, sec, data in zip(axes, securities, data_list):
            past = self.history.get_price_history(
                sec.config.key, before=interval_data.start, limit=1
            )

            past_price = data[0][1] if len(data) else None
            past_price = past[0][1] if len(past) else past_price

            if past_price:
                percent = (sec.state.price - past_price) / past_price
                ax.set_title(f"{sec.config.key} ({percent:+,.2%}%)")
            else:
                ax.set_title(sec.config.key)

        fig.tight_layout()
        return fig, axes

    def create_balance_graph(self, portfolio: Portfolio, interval: SecurityIntervals) -> tuple[Figure, Axes]:
        interval_data = self.interval_data_for(interval)

        data = self.get_balance_graph_data(portfolio.user_id, interval_data)
        fig, ax = self.create_graph(data, interval=interval_data)

        ax.set_ylabel("Balance")
        fig.tight_layout()
        return fig, ax

    def get_price_graph_data(self, ticker: str, interval: IntervalData) -> GraphData:
        """Return minimal + interval data for graphing"""
        last_before = self.history.get_price_history(ticker, before=interval.start, limit=1)
        interval_data = self.history.get_price_history(ticker, after=interval.start, before=interval.end)
        return last_before + interval_data

    def get_balance_graph_data(self, user_id: int, interval) -> GraphData:
        last_before = self.history.get_balance_history(user_id, before=interval.start, limit=1)
        interval_data = self.history.get_balance_history(user_id, after=interval.start, before=interval.end)
        return last_before + interval_data

    def create_graph(self, data: GraphData, interval: IntervalData) -> tuple[Figure, Axes]:
        fig, ax = subplots(figsize=(12, 6))

        if data:
            frame = self._prepare_graph_data(data, interval)
            self._set_graph_axes(ax, frame, interval)
        else:
            self._set_empty_graph_axes(ax)

        fig.tight_layout()
        return fig, ax

    def create_graph_matrix(self, *data: GraphData, interval: IntervalData, cols: int = 3, fig_width: int = 6, fig_height: int = 3) -> tuple[Figure, list[Axes]]:
        rows = len(data) // cols + (1 if len(data) % cols else 0)
        fig, axes = subplots(rows, cols, figsize=(fig_width * cols, fig_height * rows))

        # Fix the inconsistent return types
        axes = [axes] if isinstance(axes, Axes) else axes.flatten()

        for ax, ax_data in zip(axes, data):
            if ax_data:
                frame = self._prepare_graph_data(ax_data, interval)
                self._set_graph_axes(ax, frame, interval)
            else:
                self._set_empty_graph_axes(ax)

        for i in range(len(data), len(axes)):
            fig.delaxes(axes[i])

        fig.tight_layout()
        return fig, axes[:len(data)]

    @staticmethod
    def _get_optimal_cols(num_items: int, min_cols: int = 1, max_cols: int = 5) -> int:
        """
        Calculate a good number of columns for a grid/graph.

        - Tries to make the grid roughly square.
        - Clamped between min_cols and max_cols.
        """
        if num_items <= 0:
            return min_cols
        cols = math.ceil(math.sqrt(num_items) * 1.2)
        return max(min(cols, max_cols), min_cols)

    @staticmethod
    def _set_graph_axes(ax: Axes, frame: DataFrame, interval: IntervalData):
        ax.plot(frame.index, frame["price"], marker=",", linestyle="-", drawstyle="steps-post")

        # Annotate last point
        last_point = frame.iloc[-1]
        ax.annotate(f"{last_point["price"]:,.2f}",
                    xy=(last_point.name, last_point["price"]),
                    xytext=(15, 0),
                    textcoords="offset points",
                    ha="left", va="center",
                    bbox=dict(boxstyle="round", fc="w"))

        ax.xaxis.set_major_locator(interval.locator)
        ax.xaxis.set_major_formatter(dates.DateFormatter(interval.tick_format))
        ax.set_xlim([interval.start - interval.margin, interval.end + interval.margin])

        # ax.set_xlabel("Time")
        ax.set_ylabel("Price")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, linestyle="--", alpha=0.5)
        # ax.axvspan(interval.start - interval.margin, df.index.min(), color="lightgrey", alpha=0.3)

    @staticmethod
    def _set_empty_graph_axes(ax: Axes):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12)
        ax.tick_params(
            axis="both",
            which="both",
            bottom=False,
            left=False,
            labelbottom=False,
            labelleft=False,
        )

    @staticmethod
    def _prepare_graph_data(data: GraphData, interval: IntervalData) -> DataFrame:
        # Create DataFrame
        frame = DataFrame(data, columns=["datetime", "price"])
        frame.set_index("datetime", inplace=True)
        # frame.index = to_datetime(frame.index)

        # Get the last known price before start
        last_before_start = frame[frame.index < interval.start].iloc[-1:]  # could be empty
        frame = concat([last_before_start, frame[frame.index >= interval.start]])

        # Create a full DateTimeIndex at the desired frequency
        full_index = date_range(start=interval.start, end=interval.end, freq=interval.freq)

        # Reindex and forward-fill
        # frame = frame.resample(freq).mean()
        frame = frame.reindex(full_index, method="ffill")
        frame = frame[~frame["price"].duplicated()]
        # frame.sort_index(inplace=True)

        # Ensure emd time is included
        if frame.index[-1] < interval.end:
            frame.loc[interval.end] = data[-1][1]
            frame = frame.sort_index()

        return frame
