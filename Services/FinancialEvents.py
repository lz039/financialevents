import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import xlsxwriter
import streamlit as st
import io
from pandas.api.types import (
    is_datetime64_any_dtype,
    is_numeric_dtype,
    is_object_dtype,
)

def parse_german_date(date_string):
    if pd.isna(date_string):
        return pd.NaT
    try:
        german_months = {
            'Jan': 1, 'Feb': 2, 'Mär': 3, 'Apr': 4, 'Mai': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Okt': 10, 'Nov': 11, 'Dez': 12
        }
        day, month, year = date_string.split()
        month_num = german_months[month]
        return datetime(2000 + int(year), month_num, int(day))
    except (ValueError, KeyError):
        return pd.NaT  # Return Not-a-Time for any parsing errors


def fetch_events_data():
    res = requests.get(
        f"https://www.eqs-news.com/wp/wp-admin/admin-ajax.php?lang=de&action=fetch_realtime_events_data&recordsFrom[0][api_type]=events&recordsFrom[0][category]=future&pageLimit=10000&pageNo=1&additional[is_new]=false&additional[mode]=append&loadFrom=mysql&time=")
    if (res.status_code == 200):
        soup = BeautifulSoup(res.text, 'html.parser')
        events = []
        event_divs = soup.find_all('div', class_='event')

        for event in event_divs:
            event_data = {}
            event_data['company'] = event.find('h4', class_='event__company').get_text(strip=True)
            event_data['title'] = event.find('p', class_='event__title').get_text(strip=True)
            # event_data['location'] = event.find('div', class_='event__location').get_text(strip=True) if event.find('div', class_='event__location') else None
            date = event.find('p', class_='event__date').get_text(strip=True)
            month_year = event.find('p', class_='event__month-year').get_text(strip=True)
            event_data['date'] = f"{date} {month_year}"
            # event_data['company_url'] = event['data-events-company-url']
            # event_data['company_share_url'] = event['data-events-company-share-url']
            # event_data['uuid'] = event['data-events-uuid']
            events.append(event_data)

        df = pd.DataFrame(events)
        df['dates'] = df['date'].apply(parse_german_date)
        df.drop(columns=['date'], inplace=True)

        return df


def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a UI on top of a dataframe to let viewers filter columns

    Args:
        df (pd.DataFrame): Original dataframe

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    df = df.copy()

    # Try to convert datetimes into a standard format (datetime, no timezone)
    for col in df.columns:
        if is_object_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass

        if is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)

    modification_container = st.container()

    with modification_container:
        to_filter_columns = st.multiselect("Filter dataframe on", df.columns)
        for column in to_filter_columns:
            left, right = st.columns((1, 20))
            # Treat columns with < 10 unique values as categorical
            if isinstance(df[column], pd.CategoricalDtype) or df[column].nunique() < 10:
                user_cat_input = right.multiselect(
                    f"Values for {column}",
                    df[column].unique(),
                    default=list(df[column].unique()),
                )
                df = df[df[column].isin(user_cat_input)]
            elif is_numeric_dtype(df[column]):
                _min = float(df[column].min())
                _max = float(df[column].max())
                step = (_max - _min) / 100
                user_num_input = right.slider(
                    f"Values for {column}",
                    min_value=_min,
                    max_value=_max,
                    value=(_min, _max),
                    step=step,
                )
                df = df[df[column].between(*user_num_input)]
            elif is_datetime64_any_dtype(df[column]):
                user_date_input = right.date_input(
                    f"Values for {column}",
                    value=(
                        df[column].min(),
                        df[column].max(),
                    ),
                )
                if len(user_date_input) == 2:
                    user_date_input = tuple(map(pd.to_datetime, user_date_input))
                    start_date, end_date = user_date_input
                    df = df.loc[df[column].between(start_date, end_date)]
            else:
                user_text_input = right.text_input(
                    f"Substring or regex in {column}",
                )
                if user_text_input:
                    df = df[df[column].astype(str).str.contains(user_text_input)]

    return df


def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False)
    return output.getvalue()


def main():
    st.title("Financial Events")

    df = fetch_events_data()
    st.dataframe(
        filter_dataframe(df),
        column_config={
            "dates": st.column_config.DatetimeColumn(
                "Dates",
                format="DD.MM.YY",
            )
        }
    )

    excel_file = to_excel(df)
    st.download_button(
        label="Download data as Excel",
        data=excel_file,
        file_name="financial_events.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    main()