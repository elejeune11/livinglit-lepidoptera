"""The shared statistical entries, written once by the build (04-formulas, Statistical formulas).

Given entries cite a statistics handbook; derived entries are proved by code
from them. `write()` checks each entry against the ones before it and appends
them to fields/_shared/formulas/changes.yaml.
"""
from __future__ import annotations

from .models import FormulaEntry

NIST = "https://www.itl.nist.gov/div898/handbook/"


def _c(section):
    return {"text": f"NIST/SEMATECH e-Handbook of Statistical Methods, {section}", "url": NIST}


def T(given, expect=None):
    return {"given": given, "expect": expect or {}}


GIVEN = [
    dict(formula="mean_def", kind="definition", statement="The mean is the sum of the values divided by n.",
         equations=["m = S/n"], variables={"m": "D", "S": "D", "n": "count"},
         tests=[T({"S": 10, "n": 4}, {"m": 2.5})], does_not_apply="medians or trimmed means", cites=_c("1.3.5.1 Measures of location")),
    dict(formula="sd_def", kind="definition", statement="The sample standard deviation from the sum of squares, mean and n.",
         equations=["sd = sqrt((Q - n*m^2)/(n - 1))"], variables={"sd": "D", "Q": "D**2", "m": "D", "n": "count"},
         tests=[T({"Q": 14, "m": 2, "n": 3}, {"sd": 1.0})], does_not_apply="population SD (divisor n)", cites=_c("1.3.5.6 Measures of scale")),
    dict(formula="sem_def", kind="definition", statement="The standard error of the mean is SD divided by the square root of n.",
         equations=["sem = sd/sqrt(n)"], variables={"sem": "D", "sd": "D", "n": "count"},
         tests=[T({"sd": 2, "n": 4}, {"sem": 1})], does_not_apply="a spread that is an SD or a CI", cites=_c("7.2.2 Confidence limits for the mean")),
    dict(formula="cv_def", kind="definition", statement="The coefficient of variation is SD divided by the mean.",
         equations=["cv = sd/m"], variables={"cv": "dimensionless", "sd": "D", "m": "D"},
         tests=[T({"sd": 1, "m": 4}, {"cv": 0.25})], does_not_apply="a mean of zero", cites=_c("1.3.5.6 Measures of scale")),
    dict(formula="t_two_sample_pooled", kind="definition",
         statement="Student's two-sample t statistic with pooled variance and n1 + n2 − 2 degrees of freedom.",
         equations=["sp2 = ((n1 - 1)*s1^2 + (n2 - 1)*s2^2)/(n1 + n2 - 2)", "t = (m1 - m2)/sqrt(sp2*(1/n1 + 1/n2))",
                    "df = n1 + n2 - 2"],
         variables={"sp2": "D**2", "n1": "count", "n2": "count", "s1": "D", "s2": "D", "t": "dimensionless",
                    "m1": "D", "m2": "D", "df": "count"},
         tests=[T({"m1": 3, "m2": 1, "s1": 1, "s2": 1, "n1": 2, "n2": 2}, {"sp2": 1, "t": 2, "df": 2})],
         does_not_apply="paired samples", cites=_c("1.3.5.3 Two-sample t-test for equal means")),
    dict(formula="t_two_sample_welch", kind="definition",
         statement="Welch's two-sample t statistic with Welch–Satterthwaite degrees of freedom (unequal variances).",
         equations=["t = (m1 - m2)/sqrt(s1^2/n1 + s2^2/n2)",
                    "df = (s1^2/n1 + s2^2/n2)^2/((s1^2/n1)^2/(n1 - 1) + (s2^2/n2)^2/(n2 - 1))"],
         variables={"t": "dimensionless", "m1": "D", "m2": "D", "s1": "D", "s2": "D", "n1": "count", "n2": "count",
                    "df": "count"},
         tests=[T({"m1": 3, "m2": 1, "s1": 1, "s2": 1, "n1": 2, "n2": 2}, {"t": 2, "df": 2})],
         does_not_apply="paired samples", cites=_c("1.3.5.3 Two-sample t-test for equal means")),
    dict(formula="t_paired", kind="definition", statement="The paired t statistic from the mean and SD of differences.",
         equations=["t = md/(sdd/sqrt(n))", "df = n - 1"],
         variables={"t": "dimensionless", "md": "D", "sdd": "D", "n": "count", "df": "count"},
         tests=[T({"md": 2, "sdd": 2, "n": 4}, {"t": 2, "df": 3})], does_not_apply="independent samples",
         cites=_c("7.3.1 Do two processes have the same mean?")),
    dict(formula="one_way_anova_f", kind="definition", statement="The one-way ANOVA F is the between-group mean square over the within-group mean square.",
         equations=["F = (SSB/(k - 1))/(SSW/(N - k))", "df1 = k - 1", "df2 = N - k"],
         variables={"F": "dimensionless", "SSB": "D**2", "SSW": "D**2", "k": "count", "N": "count", "df1": "count", "df2": "count"},
         tests=[T({"SSB": 8, "SSW": 6, "k": 3, "N": 9}, {"F": 4, "df1": 2, "df2": 6})], does_not_apply="two-way designs",
         cites=_c("7.4.3.3 The ANOVA table and tests of hypotheses about means")),
    dict(formula="t_distribution", kind="model", statement="Two-sided P of a t statistic with df degrees of freedom.",
         equations=["p = tdist_p2(t, df)"], variables={"p": "dimensionless", "t": "dimensionless", "df": "count"},
         assumes=["normality", "independence"], tests=[T({"t": 2.0, "df": 10}, {"p": 0.07338803477074436})],
         does_not_apply="rank tests", cites=_c("1.3.6.6.4 t distribution")),
    dict(formula="f_distribution", kind="model", statement="Upper-tail P of an F statistic with df1 and df2 degrees of freedom.",
         equations=["p = fdist_p(F, df1, df2)"], variables={"p": "dimensionless", "F": "dimensionless", "df1": "count", "df2": "count"},
         assumes=["normality", "independence", "equal variances"], tests=[T({"F": 4, "df1": 2, "df2": 6}, {"p": 0.07871720116618075})],
         does_not_apply="non-parametric tests", cites=_c("1.3.6.6.5 F distribution")),
    dict(formula="chi2_distribution", kind="model", statement="Upper-tail P of a chi-squared statistic.",
         equations=["p = chi2_p(x, df)"], variables={"p": "dimensionless", "x": "dimensionless", "df": "count"},
         assumes=["independence", "large expected counts"], tests=[T({"x": 3.841458820694124, "df": 1}, {"p": 0.05})],
         does_not_apply="small expected counts", cites=_c("1.3.6.6.6 Chi-square distribution")),
    dict(formula="normal_distribution", kind="model", statement="Two-sided P of a z statistic.",
         equations=["p = norm_p2(z)"], variables={"p": "dimensionless", "z": "dimensionless"},
         assumes=["normality", "independence"], tests=[T({"z": 1.959963984540054}, {"p": 0.05})],
         does_not_apply="small samples with unknown variance", cites=_c("1.3.6.6.1 Normal distribution")),
    dict(formula="ci95_halfwidth", kind="model", statement="The 95 % confidence half-width of a mean.",
         equations=["h = tq975(n - 1)*sd/sqrt(n)"], variables={"h": "D", "sd": "D", "n": "count"},
         assumes=["normality", "independence"], tests=[T({"sd": 2, "n": 4}, {"h": 3.182446305284263})],
         does_not_apply="bootstrap intervals", cites=_c("7.2.2.1 Confidence interval approach")),
    dict(formula="propagated_spread_ratio", kind="model",
         statement="First-order propagation of independent relative spreads through a ratio or product.",
         equations=["sy/y = sqrt((sa/a)^2 + (sb/b)^2)"],
         variables={"sy": "D3", "y": "D3", "sa": "D", "a": "D", "sb": "D2", "b": "D2"},
         assumes=["first order", "inputs independent"], tests=[T({"sa": 3, "a": 4, "sb": 0, "b": 1, "y": 4}, {"sy": 3})],
         does_not_apply="correlated inputs", cites=_c("2.5.5 Propagation of error considerations")),
]

# Added after the rebuild check-in (08, decision 23): post-hoc tests and the two-way ANOVA F, checked from points only.
POSTHOC = [
    dict(formula="studentized_range_distribution", kind="model",
         statement="Upper-tail P of the studentized range q for k means and df error degrees of freedom.",
         equations=["p = qrange_p(q, k, df)"], variables={"p": "dimensionless", "q": "dimensionless", "k": "count", "df": "count"},
         assumes=["normality", "independence", "equal variances"], tests=[T({"q": 3.5, "k": 3, "df": 20}, {"p": 0.055891849081750045})],
         does_not_apply="comparisons against one control (Dunnett)", cites=_c("7.4.7.1 Tukey's method")),
    dict(formula="tukey_kramer_q", kind="definition",
         statement="The Tukey–Kramer q for two of k group means, from the pooled within-group mean square MSW with N − k degrees of freedom.",
         equations=["q = Abs(m1 - m2)/sqrt(MSW/2*(1/n1 + 1/n2))", "df = N - k"],
         variables={"q": "dimensionless", "m1": "D", "m2": "D", "MSW": "D**2", "n1": "count", "n2": "count",
                    "df": "count", "N": "count", "k": "count"},
         tests=[T({"m1": 3, "m2": 1, "MSW": 2, "n1": 2, "n2": 2, "N": 6, "k": 3}, {"q": 2, "df": 3})],
         does_not_apply="unequal variances (Games–Howell)", cites=_c("7.4.7.1 Tukey's method")),
    dict(formula="games_howell_q", kind="definition",
         statement="The Games–Howell q for two of k group means without assuming equal variances, with Welch–Satterthwaite degrees of freedom.",
         equations=["qgh = Abs(m1 - m2)/sqrt((s1^2/n1 + s2^2/n2)/2)",
                    "df = (s1^2/n1 + s2^2/n2)^2/((s1^2/n1)^2/(n1 - 1) + (s2^2/n2)^2/(n2 - 1))"],
         variables={"qgh": "dimensionless", "m1": "D", "m2": "D", "s1": "D", "s2": "D", "n1": "count", "n2": "count", "df": "count"},
         tests=[T({"m1": 3, "m2": 1, "s1": 1, "s2": 1, "n1": 2, "n2": 2}, {"qgh": 2.8284271247461903, "df": 2})],
         does_not_apply="equal variances assumed (Tukey–Kramer)",
         cites={"text": "Games PA, Howell JF. Pairwise multiple comparison procedures with unequal n's and/or variances. J Educ Stat 1:113–125 (1976)",
                "url": "https://doi.org/10.3102/10769986001002113"}),
    dict(formula="bonferroni_adjust", kind="definition", statement="The Bonferroni-adjusted P of one of m comparisons.",
         equations=["pb = Min(1, m*p)"], variables={"pb": "dimensionless", "p": "dimensionless", "m": "count"},
         tests=[T({"p": 0.01, "m": 3}, {"pb": 0.03})], does_not_apply="step-down procedures", cites=_c("7.4.7.3 Bonferroni's method")),
    dict(formula="sidak_adjust", kind="definition", statement="The Šidák-adjusted P of one of m independent comparisons.",
         equations=["ps = 1 - (1 - p)^m"], variables={"ps": "dimensionless", "p": "dimensionless", "m": "count"},
         tests=[T({"p": 0.01, "m": 3}, {"ps": 0.029701})], does_not_apply="step-down procedures", cites=_c("7.4.7.3 Bonferroni's method")),
    dict(formula="holm_step", kind="definition",
         statement="Holm's step-down adjustment of the i-th smallest of m P values; code keeps the adjusted values monotone.",
         equations=["ph = Min(1, (m - i + 1)*p)"], variables={"ph": "dimensionless", "p": "dimensionless", "m": "count", "i": "count"},
         tests=[T({"p": 0.01, "m": 3, "i": 1}, {"ph": 0.03})], does_not_apply="single-step procedures",
         cites={"text": "Holm S. A simple sequentially rejective multiple test procedure. Scand J Stat 6:65–70 (1979)",
                "url": "https://www.jstor.org/stable/4615733"}),
    dict(formula="holm_sidak_step", kind="definition",
         statement="The Holm–Šidák step-down adjustment of the i-th smallest of m P values; code keeps the adjusted values monotone.",
         equations=["phs = 1 - (1 - p)^(m - i + 1)"], variables={"phs": "dimensionless", "p": "dimensionless", "m": "count", "i": "count"},
         tests=[T({"p": 0.01, "m": 3, "i": 1}, {"phs": 0.029701})], does_not_apply="single-step procedures",
         cites={"text": "Holm S. A simple sequentially rejective multiple test procedure. Scand J Stat 6:65–70 (1979)",
                "url": "https://www.jstor.org/stable/4615733"}),
    dict(formula="two_way_anova_f", kind="definition",
         statement="In a two-way ANOVA, the F of a main effect or the interaction is its mean square over the error mean square.",
         equations=["F = (SS/df)/(SSE/dfE)"], variables={"F": "dimensionless", "SS": "D**2", "df": "count", "SSE": "D**2", "dfE": "count"},
         tests=[T({"SS": 8, "df": 1, "SSE": 12, "dfE": 6}, {"F": 4})], does_not_apply="repeated measures or mixed models",
         cites=_c("7.4.3.6 Two-way crossed ANOVA")),
]

DERIVED = [
    dict(formula="constant_scaling_mean", kind="derived", statement="Under y = c·x, the mean scales by c.",
         equations=["my = c*mx"], variables={"my": "D2", "mx": "D", "c": "D2/D", "Sx": "D", "Sy": "D2", "n": "count"},
         uses=[{"formula": "mean_def", "subs": {"m": "mx", "S": "Sx"}}, {"formula": "mean_def", "subs": {"m": "my", "S": "Sy"}}],
         assumes=["Sy = c*Sx"], tests=[T({"c": 2, "mx": 3}, {"my": 6})], does_not_apply="a factor that differs between samples"),
    dict(formula="constant_scaling_t", kind="derived",
         statement="Under y = c·x (c > 0) applied to both groups, means and SDs scale by c and t is unchanged, so P is unchanged.",
         equations=["ty = tx"],
         variables={"ty": "dimensionless", "tx": "dimensionless", "c": "dimensionless", "a1": "D", "a2": "D", "u1": "D",
                    "u2": "D", "b1": "D", "b2": "D", "v1": "D", "v2": "D", "n1": "count", "n2": "count",
                    "dfx": "count", "dfy": "count"},
         uses=[{"formula": "t_two_sample_welch", "subs": {"t": "tx", "m1": "a1", "m2": "a2", "s1": "u1", "s2": "u2", "df": "dfx"}},
               {"formula": "t_two_sample_welch", "subs": {"t": "ty", "m1": "b1", "m2": "b2", "s1": "v1", "s2": "v2", "df": "dfy"}}],
         assumes=["b1 = c*a1", "b2 = c*a2", "v1 = c*u1", "v2 = c*u2"],
         tests=[T({"tx": 2.5}, {"ty": 2.5})], does_not_apply="a factor that differs between groups"),
    dict(formula="constant_shift_t", kind="derived", statement="Under y = x + c applied to both groups, t and P are unchanged.",
         equations=["ty = tx"],
         variables={"ty": "dimensionless", "tx": "dimensionless", "c": "D", "a1": "D", "a2": "D", "u1": "D",
                    "u2": "D", "b1": "D", "b2": "D", "n1": "count", "n2": "count", "dfx": "count", "dfy": "count"},
         uses=[{"formula": "t_two_sample_welch", "subs": {"t": "tx", "m1": "a1", "m2": "a2", "s1": "u1", "s2": "u2", "df": "dfx"}},
               {"formula": "t_two_sample_welch", "subs": {"t": "ty", "m1": "b1", "m2": "b2", "s1": "u1", "s2": "u2", "df": "dfy"}}],
         assumes=["b1 = a1 + c", "b2 = a2 + c"], tests=[T({"tx": 1.5}, {"ty": 1.5})],
         does_not_apply="a shift that differs between groups"),
    dict(formula="ratio_of_means_constant_denominator", kind="derived",
         statement="The mean of ratios equals the ratio of means only when the denominator is one constant.",
         equations=["mr = ma/b"], variables={"mr": "D/D2", "ma": "D", "b": "D2", "Sr": "D/D2", "Sa": "D", "n": "count"},
         uses=[{"formula": "mean_def", "subs": {"m": "mr", "S": "Sr"}}, {"formula": "mean_def", "subs": {"m": "ma", "S": "Sa"}}],
         assumes=["Sr = Sa/b"], tests=[T({"ma": 6, "b": 2}, {"mr": 3})], does_not_apply="a denominator that varies by sample"),
    dict(formula="normalized_to_own_control", kind="derived",
         statement="A control normalized to its own mean has mean 1 (and SD 0 if each sample is normalized to itself).",
         equations=["my = 1"], variables={"my": "dimensionless", "mx": "D", "Sx": "D", "Sy": "dimensionless", "n": "count"},
         uses=[{"formula": "mean_def", "subs": {"m": "mx", "S": "Sx"}}, {"formula": "mean_def", "subs": {"m": "my", "S": "Sy"}}],
         assumes=["Sy = Sx/mx"], tests=[T({"mx": 5}, {"my": 1})], does_not_apply="normalized to another group's mean"),
]


def entries() -> list[FormulaEntry]:
    return [FormulaEntry.model_validate(d) for d in GIVEN + DERIVED + POSTHOC]


def write_posthoc(root=None) -> list[str]:
    """Append the post-hoc entries to the shared log as a new version (decision 23)."""
    from . import FIELDS_DIR, DEFAULT_FIELD
    from .formulas import check_entry, append_entries, load_library
    root = root or FIELDS_DIR
    lib = load_library(DEFAULT_FIELD, root)
    new = [FormulaEntry.model_validate(d) for d in POSTHOC if d["formula"] not in lib.entries]
    probs = []
    for e in new:
        probs += check_entry(e, lib)
        lib.entries[e.formula] = e
    if not probs and new:
        append_entries(new, root / "_shared" / "formulas", paper=None,
                       agent={"model": "build", "instructions": "04-formulas, Statistical formulas (decision 23)"})
    return probs


def write(root=None) -> list[str]:
    from . import FIELDS_DIR
    from .formulas import Library, check_entry, append_entries
    root = root or FIELDS_DIR
    d = root / "_shared" / "formulas"
    lib = Library()
    probs = []
    for e in entries():
        p = check_entry(e, lib)
        probs += p
        lib.entries[e.formula] = e
    if not probs:
        if (d / "changes.yaml").exists():
            (d / "changes.yaml").unlink()
        append_entries(entries(), d, paper=None, agent={"model": "build", "instructions": "04-formulas, Statistical formulas"})
    return probs
