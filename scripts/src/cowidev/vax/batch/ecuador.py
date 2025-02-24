import pandas as pd

from cowidev.utils.clean import clean_date_series
from cowidev.vax.utils.checks import VACCINES_ONE_DOSE
from cowidev.vax.utils.files import export_metadata


class Ecuador:
    def __init__(self):
        """Constructor.

        Args:
            source_url (str): Source data url
            location (str): Location name
            columns_rename (dict, optional): Maps original to new names. Defaults to None.
        """
        self.source_url_ref = "https://github.com/andrab/ecuacovid"
        self.source_url = f"{self.source_url_ref}/raw/master/datos_crudos/vacunometro/fabricantes.csv"
        self.location = "Ecuador"
        self.columns_rename = {
            "fabricante": "vaccine",
            "dosis_total": "total_vaccinations",
            "primera_dosis": "people_vaccinated",
            "segunda_dosis": "people_fully_vaccinated",
            "administered_at": "date",
        }
        self.vaccine_mapping = {
            "Pfizer/BioNTech": "Pfizer/BioNTech",
            "Sinovac": "Sinovac",
            "Oxford/AstraZeneca": "Oxford/AstraZeneca",
            "Cansino": "CanSino",
        }

    def read(self) -> pd.DataFrame:
        url = f"{self.source_url}/raw/master/datos_crudos/vacunometro/fabricantes.csv"
        return pd.read_csv(self.source_url)

    def pipe_check_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        n_columns = df.shape[1]
        if n_columns != 6:
            raise ValueError(f"The provided input does not have {6} columns. It has n_columns columns")
        return df

    def pipe_column_rename(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.columns_rename:
            return df.rename(columns=self.columns_rename)
        return df

    def pipe_vaccines(self, df: pd.DataFrame) -> pd.DataFrame:
        # Check vaccines
        vaccines_wrong = set(df.vaccine).difference(self.vaccine_mapping)
        if vaccines_wrong:
            raise ValueError(f"Unknown vaccine(s) {vaccines_wrong}")
        return df.assign(vaccine=df.vaccine.replace(self.vaccine_mapping))

    def pipe_date(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(date=clean_date_series(df.date, "%d/%m/%Y"))

    def pipe_check_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        x = df.groupby("vaccine").sum()
        if not (x["total_vaccinations"] == x[["people_vaccinated", "people_fully_vaccinated"]].sum(axis=1)).all():
            raise ValueError(f"`total_vaccinations = people_vaccinated + people_fully_vaccinated` not valid!")
        vax_1d = x.index.intersection(VACCINES_ONE_DOSE)
        if not (x.loc[vax_1d, "people_vaccinated"] == 0).all():
            raise ValueError(
                f"First doses for one dose vaccines should be 0, as they are only counted in second doses."
            )
        return df

    def pipe_aggregate_zonas(self, df: pd.DataFrame) -> pd.DataFrame:
        # Aggregate zones
        df = df.drop(columns=["zona"])
        df = df.groupby(["vaccine", "date"], as_index=False).sum()
        return df

    def pipeline_base(self, df: pd.DataFrame) -> pd.DataFrame:
        return (
            df.pipe(self.pipe_check_columns)
            .pipe(self.pipe_column_rename)
            .pipe(self.pipe_vaccines)
            .pipe(self.pipe_date)
            .pipe(self.pipe_check_metrics)
            .pipe(self.pipe_aggregate_zonas)
        )

    def pipeline_manufacturer(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df[["date", "vaccine", "total_vaccinations"]]
        df = df.assign(location="Ecuador")
        df = df.sort_values(["vaccine", "date"])
        return df[["location", "date", "vaccine", "total_vaccinations"]]

    def _get_single_shots(self, df: pd.DataFrame) -> pd.DataFrame:
        # Get single shots
        return df.loc[df.vaccine.isin(VACCINES_ONE_DOSE), ["date", "total_vaccinations"]].rename(
            columns={"total_vaccinations": "single_shots"}
        )

    def pipe_aggregate(self, df: pd.DataFrame) -> pd.DataFrame:
        # Get single shots
        return df.groupby("date", as_index=False).agg(
            {
                "total_vaccinations": sum,
                "people_vaccinated": sum,
                "people_fully_vaccinated": sum,
                "vaccine": lambda x: ", ".join(sorted(x.unique())),
            }
        )

    def pipe_single_shot_correction(self, df: pd.DataFrame, df_single) -> pd.DataFrame:
        # Single shot correction
        single_shots = df.merge(df_single, on="date", how="left")["single_shots"]
        df = df.assign(
            people_vaccinated=df.people_vaccinated + single_shots.fillna(0),
            total_vaccinations=df.total_vaccinations + single_shots.fillna(0),
        )
        return df

    def pipe_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.assign(location=self.location, source_url=self.source_url_ref)
        return df

    def pipe_exclude_dp(self, df: pd.DataFrame) -> pd.DataFrame:
        return df[(df.date < "2021-09-01") | (df.date > "2021-09-07")]

    def pipe_sort_date(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values("date")
        return df

    def pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        df_single = self._get_single_shots(df)
        df = (
            df.pipe(self.pipe_aggregate)
            .pipe(self.pipe_single_shot_correction, df_single)
            .pipe(self.pipe_metadata)
            .pipe(self.pipe_exclude_dp)
            .pipe(self.pipe_sort_date)
        )
        return df

    def to_csv(self, paths):
        """Generalized."""
        df = self.read().pipe(self.pipeline_base)
        # Manufacturer
        df_man = df.pipe(self.pipeline_manufacturer)
        df_man.to_csv(paths.tmp_vax_out_man(self.location), index=False)
        export_metadata(
            df_man,
            "Ministerio de Salud Pública del Ecuador (via https://github.com/andrab/ecuacovid)",
            self.source_url_ref,
            paths.tmp_vax_metadata_man,
        )
        # Main data
        df = df.pipe(self.pipeline)
        df.to_csv(paths.tmp_vax_out(self.location), index=False)


def main(paths):
    Ecuador().to_csv(paths)


if __name__ == "__main__":
    main()
