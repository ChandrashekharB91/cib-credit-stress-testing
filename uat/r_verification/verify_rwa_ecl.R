#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------------------------
# Independent re-implementation (base R, no packages) of the IRB RWA and IFRS 9 ECL calculations,
# used as User Verification Testing (UVT) evidence for the Python engine.
#
# Written from the methodology document, not translated from the Python code. It recomputes, for
# every facility, scenario and reporting date:
#   * IRB risk weight, RWA and regulatory EL from rating grade, regulatory LGD/EAD, maturity and
#     survival (grade -> PD via its own copy of the master scale; M floor/cap applied here)
#   * the annual PD curve with logit reversion, survival, maturity roll-over, partial final
#     periods, mid-period discounting, SICR/watchlist/DPD staging and Stage 1/2/3 ECL
# and compares them with the engine extracts. Exit status 1 if any difference exceeds tolerance.
#
# Usage: Rscript verify_rwa_ecl.R <verification_dir> <output_csv> [tolerance]
# -----------------------------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: verify_rwa_ecl.R <verification_dir> <output_csv> [tolerance]")
vdir <- args[1]
out_csv <- args[2]
tol <- if (length(args) >= 3) as.numeric(args[3]) else 1e-8

prm <- read.csv(file.path(vdir, "parameters.csv"))
H <- prm$horizon
CENTRAL_PD <- c(0.0005, 0.0008, 0.0013, 0.0021, 0.0035, 0.0058, 0.0095,
                0.0157, 0.0259, 0.0427, 0.0705, 0.1163, 0.2500)

grade_pd <- function(g) ifelse(g <= length(CENTRAL_PD), CENTRAL_PD[pmin(g, length(CENTRAL_PD))], 1)
logit <- function(p) log(p / (1 - p))
expit <- function(x) 1 / (1 + exp(-x))

irb_corr <- function(pd, sales, large_fi, sme_thr) {
  w <- (1 - exp(-50 * pd)) / (1 - exp(-50))
  R <- 0.12 * w + 0.24 * (1 - w)
  s <- pmin(pmax(sales, 5), 50)
  R <- R - ifelse(sales < sme_thr, 0.04 * (1 - (s - 5) / 45), 0)
  ifelse(large_fi == 1, 1.25 * R, R)
}

irb_k <- function(pd, lgd, m, R) {
  b <- (0.11852 - 0.05478 * log(pd))^2
  cond <- pnorm((qnorm(pd) + sqrt(R) * qnorm(0.999)) / sqrt(1 - R))
  pmax(lgd * cond - pd * lgd, 0) * (1 + (m - 2.5) * b) / (1 - 1.5 * b)
}

compare <- function(scen, metric, t, py, r) {
  d <- abs(py - r)
  rel <- max(d) / max(1, sum(abs(py)))
  data.frame(scenario = scen, metric = metric, t = t, n = length(py), python_total = sum(py),
             r_total = sum(r), max_abs_diff = max(d), rel_diff_of_total = rel,
             status = ifelse(rel <= tol & max(d) <= tol * max(1, max(abs(py))), "PASS", "FAIL"))
}

results <- list()
files <- list.files(vdir, pattern = "^facility_.*\\.csv$")
for (f in files) {
  scen <- sub("^facility_(.*)\\.csv$", "\\1", f)
  d <- read.csv(file.path(vdir, f), stringsAsFactors = FALSE)
  n <- nrow(d)
  col <- function(prefix) as.matrix(d[, paste0(prefix, "_", 0:H)])
  P <- col("pd"); G <- col("grade"); LGD <- col("lgd"); EAD <- col("ead"); S <- col("survival")
  m_eff <- pmin(pmax(d$maturity, prm$maturity_floor), prm$maturity_cap)
  firb <- d$approach == "F-IRB"

  # ---------------------------------------------------------------- RWA and regulatory EL
  for (t in 0:H) {
    pd_reg <- pmin(pmax(grade_pd(G[, t + 1]), prm$pd_floor), 0.9999)
    lgd_reg <- d[[paste0("lgd_reg_", t)]]
    ead_reg <- d[[paste0("ead_reg_", t)]]
    R <- irb_corr(pd_reg, d$sales, d$large_fi, prm$sme_threshold)
    rw_perf <- irb_k(pd_reg, lgd_reg, m_eff, R) * 12.5 * prm$scaling_factor
    k_def <- ifelse(firb, 0, pmax(d$lgd_downturn - LGD[, t + 1], 0))
    rwa <- (S[, t + 1] * rw_perf + (1 - S[, t + 1]) * k_def * 12.5 * prm$scaling_factor) * ead_reg
    el <- (S[, t + 1] * pd_reg * lgd_reg + (1 - S[, t + 1]) * ifelse(firb, lgd_reg, LGD[, t + 1])) * ead_reg
    results[[length(results) + 1]] <- compare(scen, "rwa", t, d[[paste0("rwa_", t)]], rwa)
    results[[length(results) + 1]] <- compare(scen, "el_reg", t, d[[paste0("el_reg_", t)]], el)
  }

  # ---------------------------------------------------------------- IFRS 9 ECL and staging
  maxlife <- prm$max_lifetime_years
  nY <- H + maxlife + 1
  p <- pmin(pmax(P, 1e-6), 1 - 1e-6)
  q <- matrix(NA_real_, n, nY)
  for (y in 1:nY) {
    if (y <= H) {
      q[, y] <- p[, y + 1]
    } else {
      w <- min(1, (y - H) / max(prm$reversion_years, 1))
      q[, y] <- expit((1 - w) * logit(p[, H + 1]) + w * logit(p[, 1]))
    }
  }
  dflt <- d$defaulted == 1
  surv <- ifelse(dflt, 0, 1)
  for (t in 0:H) {
    if (t > 0) {
      surv <- surv * (1 - q[, t])
      surv[dflt] <- 0
    }
    mt <- ifelse(d$maturity - t > 0, d$maturity - t, d$maturity)
    K <- min(ceiling(max(mt)), maxlife)
    alive <- rep(1, n); el12 <- rep(0, n); ellife <- rep(0, n)
    for (k in 1:K) {
      fr <- pmin(pmax(mt - (k - 1), 0), 1)
      qk <- 1 - (1 - q[, t + k])^fr
      cidx <- min(t + k, H) + 1
      loss <- alive * qk * LGD[, cidx] * EAD[, cidx] * (1 + d$eir)^(-(k - 1 + fr / 2))
      ellife <- ellife + loss
      if (k == 1) el12 <- loss
      alive <- alive * (1 - qk)
    }
    pd_stage <- P[, t + 1]
    sicr <- (pd_stage / pmax(d$origination_pd, 1e-6) > prm$sicr_relative_threshold) &
            (pd_stage - d$origination_pd > prm$sicr_absolute_threshold)
    stage2 <- (sicr | G[, t + 1] >= prm$watchlist_grade | d$dpd >= prm$dpd_backstop) & !dflt
    ead_t <- ifelse(dflt, EAD[, 1], EAD[, t + 1])
    ecl <- surv * ifelse(stage2, ellife, el12) + (1 - surv) * LGD[, t + 1] * ead_t
    results[[length(results) + 1]] <- compare(scen, "survival", t, S[, t + 1], surv)
    results[[length(results) + 1]] <- compare(scen, "stage2_flag", t, d[[paste0("stage2_", t)]], as.numeric(stage2))
    results[[length(results) + 1]] <- compare(scen, "ecl", t, d[[paste0("ecl_", t)]], ecl)
  }
}
res <- do.call(rbind, results)
write.csv(res, out_csv, row.names = FALSE)
cat(sprintf("R verification: %d comparisons, %d PASS, %d FAIL (tolerance %.0e)\n",
            nrow(res), sum(res$status == "PASS"), sum(res$status == "FAIL"), tol))
if (any(res$status == "FAIL")) {
  print(res[res$status == "FAIL", ])
  quit(status = 1)
}
