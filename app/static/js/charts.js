/**
 * ChartHelpers — shared Chart.js scaffolding.
 * Loaded after Chart.js CDN in base.html; exposes window.ChartHelpers.
 */
(function (global) {
  'use strict';

  function readVar(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (e) {
      return fallback;
    }
  }

  function colors() {
    return {
      accent:     readVar('--accent',          '#60a5fa'),
      accent2:    readVar('--accent-2',        '#34d399'),
      accent5:    readVar('--accent-5',        '#a78bfa'),
      primary:    readVar('--primary',         '#60a5fa'),
      muted:      readVar('--muted',           '#94a3b8'),
      grid:       readVar('--chart-grid',      'rgba(148, 163, 184, 0.12)'),
      gridAlt:    readVar('--chart-grid-alt',  'rgba(148, 163, 184, 0.08)'),
      chartBg:    readVar('--chart-bg-deep',   '#0b1220'),
      panel2:     readVar('--panel-2',         '#1e293b'),
      border:     readVar('--border',          '#334155'),
      textWhite:  readVar('--text-white',      '#ffffff'),
    };
  }

  // £ tooltip callback. decimals=0 for whole-pound, 2 for pence.
  function gbpTooltip(decimals) {
    var d = (decimals == null) ? 0 : decimals;
    return {
      callbacks: {
        label: function (ctx) {
          var label = ctx.dataset && ctx.dataset.label ? ctx.dataset.label + ': ' : '';
          return ' ' + label + '£' + ctx.parsed.y.toLocaleString('en-GB', {
            minimumFractionDigits: d,
            maximumFractionDigits: d,
          });
        }
      }
    };
  }

  /**
   * Common line-chart options. Pass { tooltip, extraScales, extra } to override.
   * - tooltip: full plugins.tooltip object (e.g. gbpTooltip(0)).
   * - extraScales: merged into scales.x / scales.y beyond the grid/ticks defaults.
   * - extra: merged into top-level options after defaults.
   */
  function lineOptions(opts) {
    opts = opts || {};
    var c = colors();
    var base = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: { grid: { color: c.grid }, ticks: { color: c.muted, font: { size: 11 } } },
        y: { grid: { color: c.grid }, ticks: { color: c.muted, font: { size: 11 } } },
      },
    };
    if (opts.tooltip) base.plugins.tooltip = opts.tooltip;
    if (opts.extraScales) {
      if (opts.extraScales.x) Object.assign(base.scales.x, opts.extraScales.x);
      if (opts.extraScales.y) Object.assign(base.scales.y, opts.extraScales.y);
    }
    if (opts.extra) Object.assign(base, opts.extra);
    return base;
  }

  /**
   * Common line dataset shape. Caller provides values + color; rest has sensible defaults.
   * - fillAlphaHex: 2-char hex appended to color for fill tint (e.g. '14', '22'). Pass null to disable fill.
   * - pointCutoff: max series length at which points are shown (beyond this, pointRadius=0).
   */
  function lineDataset(cfg) {
    cfg = cfg || {};
    var color = cfg.color;
    var values = cfg.values || [];
    var cutoff = (cfg.pointCutoff == null) ? 24 : cfg.pointCutoff;
    var hasBg = cfg.backgroundColor != null;
    var hasHex = cfg.fillAlphaHex != null;
    var fill = hasBg || hasHex;
    var bg = hasBg ? cfg.backgroundColor : (hasHex ? (color + cfg.fillAlphaHex) : 'transparent');
    return {
      data: values,
      borderColor: color,
      backgroundColor: bg,
      borderWidth: cfg.borderWidth || 2,
      pointRadius: (cfg.pointRadius != null) ? cfg.pointRadius : (values.length <= cutoff ? 3 : 0),
      pointBackgroundColor: color,
      fill: fill,
      tension: (cfg.tension != null) ? cfg.tension : 0.25,
    };
  }

  // Vertical crosshair on hover — draws a thin dashed line through the active
  // point so it's easier to read off the date/value on dense time series.
  var crosshairPlugin = {
    id: 'crosshair',
    afterDraw: function (chart) {
      var active = chart.tooltip && chart.tooltip.getActiveElements
        ? chart.tooltip.getActiveElements()
        : (chart.getActiveElements ? chart.getActiveElements() : []);
      if (!active || !active.length) return;
      var ctx = chart.ctx;
      var ca = chart.chartArea;
      var x = active[0].element.x;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x, ca.top);
      ctx.lineTo(x, ca.bottom);
      ctx.lineWidth = 1;
      ctx.strokeStyle = readVar('--muted', '#94a3b8') + '66';
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.restore();
    }
  };

  // Tooltip styling shared across the polished line charts.
  function polishedTooltip(callbacks) {
    var c = colors();
    return {
      enabled: true,
      intersect: false,
      mode: 'index',
      backgroundColor: c.panel2,
      borderColor: c.border,
      borderWidth: 1,
      padding: 10,
      cornerRadius: 8,
      titleColor: c.textWhite,
      bodyColor: c.textWhite,
      titleFont: { weight: '600', size: 12 },
      bodyFont: { size: 12 },
      boxPadding: 4,
      callbacks: callbacks || {}
    };
  }

  /**
   * Automatic initialization of charts based on data- attributes.
   * Scans for canvases with specific IDs or data attributes on load.
   */
  document.addEventListener('DOMContentLoaded', function () {
    var c = colors();

    // ── 1. Holding Detail History Chart ──────────────────────────────────────
    (function initHistoryChart() {
      var canvas = document.getElementById('historyChart');
      if (!canvas) return;
      var rawData = JSON.parse(canvas.dataset.history || '[]');
      if (!rawData.length) return;

      var labels = rawData.map(function(d) { return d.date; });
      var values = rawData.map(function(d) { return d.price; });
      var ctx = canvas.getContext('2d');

      var benchmarkRaw = canvas.dataset.benchmark ? JSON.parse(canvas.dataset.benchmark) : null;
      var benchmarkValues = benchmarkRaw ? benchmarkRaw.map(function(d) { return d.price; }) : null;

      if (typeof window.Chart === 'function') {
        var gradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
        gradient.addColorStop(0, c.accent + '33');
        gradient.addColorStop(1, c.accent + '00');

        var datasets = [{
          label: 'Price',
          data: values,
          borderColor: c.accent,
          backgroundColor: gradient,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointBackgroundColor: c.accent,
          fill: true,
          tension: 0.2
        }];

        if (benchmarkValues) {
          datasets.push({
            label: 'Benchmark',
            data: benchmarkValues,
            borderColor: 'rgba(251,191,36,0.7)',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            borderDash: [5, 4],
            pointRadius: 0,
            pointHoverRadius: 3,
            pointBackgroundColor: 'rgba(251,191,36,0.7)',
            fill: false,
            tension: 0.2
          });
        }

        new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: datasets
          },
          options: lineOptions({
            tooltip: { intersect: false, mode: 'index' },
            extraScales: {
              x: { ticks: { color: c.muted, font: { size: 11 }, maxTicksLimit: 6 } }
            }
          })
        });
      } else {
        drawFallback(canvas, values, c.accent);
      }
    })();

    // ── 2. Account Allocation Doughnut ───────────────────────────────────────
    (function initAllocChart() {
      var canvas = document.getElementById('allocChart');
      if (!canvas) return;
      var palette = JSON.parse(canvas.dataset.palette || '[]');
      var labels  = JSON.parse(canvas.dataset.labels  || '[]');
      var values  = JSON.parse(canvas.dataset.values  || '[]');
      var pcts    = JSON.parse(canvas.dataset.pcts    || '[]');
      var total   = canvas.dataset.total || '£0.00';
      var colors  = labels.map(function(_, i) { return palette[i % palette.length]; });

      if (typeof window.Chart !== 'function') return;

      var centerPlugin = {
        id: 'centerText',
        afterDraw: function(chart) {
          var ctx = chart.ctx;
          var ca  = chart.chartArea;
          var cx  = (ca.left + ca.right)  / 2;
          var cy  = (ca.top  + ca.bottom) / 2;
          var active = chart.getActiveElements();
          ctx.save();
          ctx.textAlign    = 'center';
          ctx.textBaseline = 'middle';
          if (active.length > 0) {
            var idx = active[0].index;
            var pct = pcts[idx].toFixed(1) + '%';
            var val = '£' + values[idx].toLocaleString('en-GB', {minimumFractionDigits:2, maximumFractionDigits:2});
            ctx.font      = 'bold 26px Inter, system-ui, sans-serif';
            ctx.fillStyle = c.textWhite;
            ctx.fillText(pct, cx, cy - 9);
            ctx.font      = '600 12px Inter, system-ui, sans-serif';
            ctx.fillStyle = c.muted;
            ctx.fillText(val, cx, cy + 13);
          } else {
            ctx.font      = 'bold 15px Inter, system-ui, sans-serif';
            ctx.fillStyle = c.textWhite;
            ctx.fillText(total, cx, cy - 8);
            ctx.font      = '10px Inter, system-ui, sans-serif';
            ctx.fillStyle = c.muted;
            ctx.fillText('TOTAL TRACKED', cx, cy + 10);
          }
          ctx.restore();
        }
      };

      var chart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        plugins: [centerPlugin],
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: colors,
            hoverBackgroundColor: colors,
            borderWidth: 3,
            borderColor: c.chartBg,
            hoverBorderColor: c.textWhite,
            hoverBorderWidth: 2,
            hoverOffset: 8,
          }]
        },
        options: {
          cutout: '68%',
          responsive: false,
          layout: { padding: 14 },
          animation: { animateRotate: true, duration: 700, easing: 'easeInOutQuart' },
          plugins: {
            legend:  { display: false },
            tooltip: { enabled: false },
          },
          onHover: function(event, activeElements) {
            canvas.style.cursor = activeElements.length ? 'pointer' : 'default';
            highlightAllocList(activeElements.length ? activeElements[0].index : -1, colors);
          }
        }
      });

      // Bidirectional highlight
      document.querySelectorAll('.allocation-item[data-index]').forEach(function(item) {
        item.addEventListener('mouseenter', function() {
          var idx = parseInt(item.dataset.index);
          highlightAllocList(idx, colors);
          chart.setActiveElements([{ datasetIndex: 0, index: idx }]);
          chart.update('none');
        });
        item.addEventListener('mouseleave', function() {
          highlightAllocList(-1, colors);
          chart.setActiveElements([]);
          chart.update('none');
        });
      });
    })();

    // ── 3. Account Monthly/Daily History Chart ───────────────────────────────
    (function initAcctChart() {
      var canvas = document.getElementById('acctMonthlyChart');
      if (!canvas) return;
      var dailyLabels   = JSON.parse(canvas.dataset.dailyLabels   || '[]');
      var dailyValues   = JSON.parse(canvas.dataset.dailyValues   || '[]');
      var dailyPlan7    = JSON.parse(canvas.dataset.dailyPlan7    || '[]');
      var dailyPlanG    = JSON.parse(canvas.dataset.dailyPlanglobal || '[]');
      var monthlyLabels = JSON.parse(canvas.dataset.monthlyLabels || '[]');
      var monthlyValues = JSON.parse(canvas.dataset.monthlyValues || '[]');
      var monthlyPlan7  = JSON.parse(canvas.dataset.monthlyPlan7  || '[]');
      var monthlyPlanG  = JSON.parse(canvas.dataset.monthlyPlanglobal || '[]');
      var globalRate    = parseFloat(canvas.dataset.globalRate || '0') || 0;
      var goalValue     = parseFloat(canvas.dataset.goal || '0') || 0;
      var ctx = canvas.getContext('2d');
      var chartInstance = null;

      function parseYMD(s) {
        if (!s) return null;
        var parts = String(s).split('-');
        if (parts.length < 3) return null;
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      }
      function parseYM(s) {
        if (!s) return null;
        var parts = String(s).split('-');
        if (parts.length < 2) return null;
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, 1);
      }
      function fmtDayMonth(d) {
        return d ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '';
      }
      function fmtMonthYear(d) {
        return d ? d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '';
      }
      function fmtFull(d) {
        return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      }

      function getSlice(mode, range) {
        var src = mode === 'daily'
          ? { labels: dailyLabels, values: dailyValues, plan7: dailyPlan7, planG: dailyPlanG }
          : { labels: monthlyLabels, values: monthlyValues, plan7: monthlyPlan7, planG: monthlyPlanG };
        if (!range || range <= 0 || range >= src.labels.length) return src;
        return {
          labels: src.labels.slice(-range),
          values: src.values.slice(-range),
          plan7:  src.plan7.slice(-range),
          planG:  src.planG.slice(-range),
        };
      }

      function fmtGBP(v) {
        if (v == null || !isFinite(v)) return '—';
        return '£' + Number(v).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      }

      function updateStats(slice) {
        var lastActual = slice.values.length ? slice.values[slice.values.length - 1] : null;
        var lastPlan7  = slice.plan7.length  ? slice.plan7[slice.plan7.length - 1]  : null;
        var diff       = (lastActual != null && lastPlan7 != null) ? lastActual - lastPlan7 : null;

        var elA = document.getElementById('acctStatActual');
        var elP = document.getElementById('acctStatPlan7');
        var elD = document.getElementById('acctStatDiff7');
        var elG = document.getElementById('acctStatGoal');

        if (elA) elA.textContent = fmtGBP(lastActual);
        if (elP) elP.textContent = fmtGBP(lastPlan7);
        if (elD) {
          if (diff == null) { elD.textContent = '—'; elD.className = 'm-0 text-bold'; }
          else {
            elD.textContent = (diff >= 0 ? '+' : '') + fmtGBP(diff);
            elD.className = 'm-0 text-bold ' + (diff >= 0 ? 'perf-positive' : 'perf-negative');
          }
        }

        if (elG) {
          if (!isFinite(goalValue) || goalValue <= 0 || lastActual == null) {
            elG.textContent = '—';
          } else {
            var remaining = goalValue - lastActual;
            elG.textContent = remaining > 0 ? fmtGBP(remaining) : 'goal hit';
          }
        }
      }

      function renderChart(mode, range) {
        var d = getSlice(mode, range);
        var rawLabels = d.labels;
        var displayLabels = rawLabels.map(function (s) {
          return mode === 'daily' ? fmtDayMonth(parseYMD(s)) : fmtMonthYear(parseYM(s));
        });
        if (typeof window.Chart === 'function') {
          if (chartInstance) {
            chartInstance.data.labels = displayLabels;
            chartInstance.data.datasets[0].data = d.values;
            if (chartInstance.data.datasets[1]) chartInstance.data.datasets[1].data = d.plan7;
            if (chartInstance.data.datasets[2]) {
              chartInstance.data.datasets[2].data = d.planG;
              chartInstance.data.datasets[2].label = 'Plan (' + (globalRate * 100).toFixed(1) + '%)';
              chartInstance.data.datasets[2].hidden = !(d.planG && d.planG.length && globalRate && Math.abs(globalRate - 0.07) > 0.0001);
            }
            chartInstance.update();
          } else {
            var datasets = [
              (function() {
                var gradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
                gradient.addColorStop(0, c.accent2 + '33');
                gradient.addColorStop(1, c.accent2 + '00');
                return {
                  label: 'Actual',
                  data: d.values,
                  borderColor: c.accent2,
                  backgroundColor: gradient,
                  borderWidth: 2,
                  pointRadius: 0,
                  pointHoverRadius: 4,
                  pointBackgroundColor: c.accent2,
                  pointHoverBackgroundColor: c.accent2,
                  pointHoverBorderColor: c.textWhite,
                  pointHoverBorderWidth: 2,
                  fill: true,
                  tension: 0.25,
                };
              })(),
              {
                label: 'Plan (7%)',
                data: d.plan7,
                borderColor: c.muted + 'AA',
                borderDash: [6, 5],
                backgroundColor: 'transparent',
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: c.muted,
                pointHoverBorderColor: c.textWhite,
                pointHoverBorderWidth: 2,
                borderWidth: 1.5,
              },
              {
                label: 'Plan (' + (globalRate * 100).toFixed(1) + '%)',
                data: d.planG,
                borderColor: c.accent5 + 'AA',
                borderDash: [2, 5],
                backgroundColor: 'transparent',
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: c.accent5,
                pointHoverBorderColor: c.textWhite,
                pointHoverBorderWidth: 2,
                borderWidth: 1.5,
                hidden: !(d.planG && d.planG.length && globalRate && Math.abs(globalRate - 0.07) > 0.0001),
              },
            ];
            var opts = lineOptions({
              tooltip: polishedTooltip({
                title: function (items) {
                  var idx = items && items[0] ? items[0].dataIndex : -1;
                  var raw = idx >= 0 ? rawLabels[idx] : '';
                  if (mode === 'daily') return fmtFull(parseYMD(raw)) || raw;
                  return fmtMonthYear(parseYM(raw)) || raw;
                },
                label: function(ctx2) {
                  return ' ' + ctx2.dataset.label + ': £' + Math.round(ctx2.parsed.y).toLocaleString('en-GB');
                }
              }),
              extraScales: {
                x: { grid: { color: c.gridAlt }, ticks: { color: c.muted, maxRotation: 0, maxTicksLimit: 6 } },
                y: { grid: { color: c.gridAlt }, ticks: { color: c.muted, callback: function(v) { return v >= 1000 ? '£' + (v/1000).toFixed(0) + 'k' : '£' + Math.round(v); } } }
              },
              extra: { interaction: { mode: 'index', intersect: false } }
            });
            chartInstance = new Chart(ctx, {
              type: 'line',
              plugins: [crosshairPlugin],
              data: {
                labels: displayLabels,
                datasets: datasets
              },
              options: opts
            });
          }
        } else {
          drawFallback(canvas, d.values, c.accent2);
        }
        updateStats(d);
      }

      var pills = document.querySelectorAll('.chart-range-pill');
      var activePill = document.querySelector('.chart-range-pill-active');
      if (activePill) {
        renderChart(activePill.dataset.mode || 'daily', parseInt(activePill.dataset.range) || 0);
      } else if (pills.length) {
        renderChart(pills[0].dataset.mode || 'daily', parseInt(pills[0].dataset.range) || 0);
      }

      pills.forEach(function(pill) {
        pill.addEventListener('click', function() {
          pills.forEach(function(p) { p.classList.remove('chart-range-pill-active'); });
          pill.classList.add('chart-range-pill-active');
          renderChart(pill.dataset.mode || 'daily', parseInt(pill.dataset.range) || 0);
        });
      });
    })();

    // ── 4. Performance Chart ────────────────────────────────────────────────
    (function initPerfChart() {
      var canvas = document.getElementById('perfChart');
      if (!canvas || typeof window.Chart !== 'function') return;
      var allLabels = JSON.parse(canvas.dataset.labels || '[]');  // YYYY-MM-DD
      var allActual = JSON.parse(canvas.dataset.actual || '[]');
      var allPlan   = JSON.parse(canvas.dataset.plan   || '[]');
      var assumedRate = canvas.dataset.assumedRate || '';
      if (!allLabels.length) return;

      var periods = { '1M': 30, '6M': 180, '1Y': 365, 'ALL': 999999 };
      var chart = null;

      function parseYMD(s) {
        if (!s) return null;
        var parts = s.split('-');
        if (parts.length < 3) return null;
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      }
      function fmtDayMonth(d) {
        return d ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '';
      }
      function fmtFull(d) {
        return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      }

      function sliceByPeriod(period) {
        var days = periods[period] || 999999;
        if (days >= allLabels.length) return { labels: allLabels, actual: allActual, plan: allPlan };
        var start = Math.max(0, allLabels.length - days);
        return {
          labels: allLabels.slice(start),
          actual: allActual.slice(start),
          plan:   allPlan.slice(start),
        };
      }

      function formatGBP(v, decimals) {
        if (v == null || !isFinite(v)) return '—';
        return '£' + Number(v).toLocaleString('en-GB', { minimumFractionDigits: decimals || 0, maximumFractionDigits: decimals || 0 });
      }

      function updateStats(slice) {
        var lastActual = slice.actual.length ? slice.actual[slice.actual.length - 1] : null;
        var lastPlan   = slice.plan.length   ? slice.plan[slice.plan.length - 1]     : null;
        var firstActual = slice.actual.length ? slice.actual[0] : null;
        var diff = (lastActual != null && lastPlan != null) ? lastActual - lastPlan : null;
        var growth = (firstActual && firstActual !== 0 && lastActual != null) ? (lastActual - firstActual) / firstActual * 100 : null;

        var elA = document.getElementById('perfStatActual');
        var elP = document.getElementById('perfStatPlan');
        var elD = document.getElementById('perfStatDiff');
        var elG = document.getElementById('perfStatGrowth');
        if (elA) elA.textContent = formatGBP(lastActual);
        if (elP) elP.textContent = formatGBP(lastPlan);
        if (elD) {
          if (diff == null) { elD.textContent = '—'; elD.className = 'm-0 text-bold'; }
          else {
            elD.textContent = (diff >= 0 ? '+' : '') + formatGBP(diff).replace('£', '£');
            elD.className = 'm-0 text-bold ' + (diff >= 0 ? 'perf-positive' : 'perf-negative');
          }
        }
        if (elG) {
          if (growth == null) { elG.textContent = '—'; elG.className = 'm-0 text-bold'; }
          else {
            elG.textContent = (growth >= 0 ? '+' : '') + growth.toFixed(2) + '%';
            elG.className = 'm-0 text-bold ' + (growth >= 0 ? 'perf-positive' : 'perf-negative');
          }
        }
      }

      function render(period) {
        var slice = sliceByPeriod(period);
        var displayLabels = slice.labels.map(function (s) { return fmtDayMonth(parseYMD(s)); });
        var ctx = canvas.getContext('2d');
        var h = canvas.clientHeight || canvas.height || 280;
        var grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, c.accent2 + '55');
        grad.addColorStop(1, c.accent2 + '00');

        var datasets = [
          {
            label: 'Actual',
            data: slice.actual,
            borderColor: c.accent2,
            backgroundColor: grad,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: c.accent2,
            pointHoverBorderColor: c.textWhite,
            pointHoverBorderWidth: 2,
            borderWidth: 2.5,
          },
          {
            label: 'Plan (' + assumedRate + '%)',
            data: slice.plan,
            borderColor: c.muted + 'AA',
            borderDash: [6, 5],
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: c.muted,
            pointHoverBorderColor: c.textWhite,
            pointHoverBorderWidth: 2,
            borderWidth: 1.5,
          },
        ];

        if (chart) chart.destroy();
        chart = new Chart(canvas, {
          type: 'line',
          plugins: [crosshairPlugin],
          data: { labels: displayLabels, datasets: datasets },
          options: lineOptions({
            tooltip: polishedTooltip({
              title: function (items) {
                var idx = items && items[0] ? items[0].dataIndex : -1;
                var raw = idx >= 0 ? slice.labels[idx] : '';
                return fmtFull(parseYMD(raw)) || raw;
              },
              label: function(ctx2) {
                return ' ' + ctx2.dataset.label + ': £' + Math.round(ctx2.parsed.y).toLocaleString('en-GB');
              }
            }),
            extraScales: {
              x: { grid: { color: c.gridAlt }, ticks: { color: c.muted, maxRotation: 0, maxTicksLimit: 6 } },
              y: { grid: { color: c.gridAlt }, ticks: { color: c.muted, callback: function(v) { return v >= 1000 ? '£' + (v/1000).toFixed(0) + 'k' : '£' + Math.round(v); } } }
            },
            extra: { interaction: { mode: 'index', intersect: false } }
          })
        });

        updateStats(slice);
      }

      // Scope period buttons to the card containing the perf chart so we don't
      // collide with overview's identical button class.
      var perfBtns = Array.prototype.filter.call(
        document.querySelectorAll('.period-selector .period-btn'),
        function (b) {
          var card = b.closest('.card');
          return card && card.querySelector('#perfChart');
        }
      );
      perfBtns.forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          perfBtns.forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
          render(btn.dataset.period);
        });
      });

      var initial = (Array.prototype.find.call(perfBtns, function (b) { return b.classList.contains('active'); }) || {}).dataset;
      render((initial && initial.period) || 'ALL');
    })();

    // ── 5. Projections Chart ────────────────────────────────────────────────
    (function initProjectionChart() {
      var canvas = document.getElementById('projectionChart');
      if (!canvas || typeof window.Chart !== 'function') return;
      var labels = JSON.parse(canvas.dataset.labels || '[]');
      var values = JSON.parse(canvas.dataset.values || '[]');

      new Chart(canvas, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [lineDataset({
            values: values,
            color: c.accent2,
            fillAlphaHex: '12',
            pointCutoff: 20,
            tension: 0.3,
          })]
        },
        options: lineOptions({
          tooltip: gbpTooltip(0),
          extraScales: {
            x: { ticks: { color: c.muted, font: { size: 11 }, maxTicksLimit: 10 } },
            y: { ticks: { color: c.muted, font: { size: 11 }, callback: function(v) { return '£' + (v/1000).toFixed(0) + 'k'; } } }
          }
        })
      });
    })();

    // ── 6. Overview Allocation Chart ─────────────────────────────────────────
    (function initOverviewAllocChart() {
      var canvas = document.getElementById('allocationChart');
      if (!canvas || typeof window.Chart !== 'function') return;
      var labels = JSON.parse(canvas.dataset.labels || '[]');
      var values = JSON.parse(canvas.dataset.values || '[]');
      var palette = [
        c.accent, c.accent2,
        '#f59e0b', '#10b981', '#8b5cf6', '#ef4444',
        '#06b6d4', '#f97316', '#84cc16', '#ec4899',
        '#6366f1', '#14b8a6',
      ];

      labels.forEach(function(_, i) {
        document.querySelectorAll('.alloc-dot-' + i).forEach(function(el) {
          el.style.background = palette[i % palette.length];
        });
      });

      function highlightRow(idx) {
        document.querySelectorAll('.allocation-legend-row[data-index]').forEach(function(row) {
          var i = parseInt(row.dataset.index);
          if (idx >= 0 && i === idx) {
            var col = palette[i % palette.length];
            row.style.outline = '1px solid ' + col;
            row.style.boxShadow = '0 0 0 1px ' + col + '55, 0 4px 16px ' + col + '25';
            row.style.transform = 'translateX(4px)';
          } else {
            row.style.outline = '';
            row.style.boxShadow = '';
            row.style.transform = '';
          }
        });
      }

      var chart = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: palette.slice(0, labels.length),
            hoverBackgroundColor: palette.slice(0, labels.length),
            borderWidth: 2,
            borderColor: c.panel2 || '#1e293b',
            hoverBorderColor: '#ffffff',
            hoverBorderWidth: 2,
            hoverOffset: 8,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: c.panel2,
              borderColor: c.border,
              borderWidth: 1,
              callbacks: {
                label: function(ctx) {
                  var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
                  var pct = total > 0 ? (ctx.parsed / total * 100).toFixed(1) : '0.0';
                  return ' £' + Math.round(ctx.parsed).toLocaleString('en-GB') + ' (' + pct + '%)';
                }
              }
            }
          },
          onHover: function(event, activeElements) {
            canvas.style.cursor = activeElements.length ? 'pointer' : 'default';
            highlightRow(activeElements.length ? activeElements[0].index : -1);
          }
        }
      });

      document.querySelectorAll('.allocation-legend-row[data-index]').forEach(function(row) {
        row.addEventListener('mouseenter', function() {
          var idx = parseInt(row.dataset.index);
          highlightRow(idx);
          chart.setActiveElements([{ datasetIndex: 0, index: idx }]);
          chart.update('none');
        });
        row.addEventListener('mouseleave', function() {
          highlightRow(-1);
          chart.setActiveElements([]);
          chart.update('none');
        });
      });
    })();

    // ── 7. Overview Net Worth Chart ──────────────────────────────────────────
    (function initNetWorthChart() {
      var canvas = document.getElementById('netWorthChart');
      if (!canvas || typeof window.Chart !== 'function') return;
      var labels = JSON.parse(canvas.dataset.labels || '[]');
      var values = JSON.parse(canvas.dataset.values || '[]');

      var fmtLabels = labels.map(function(k) {
        var parts = k.split('-');
        var d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, 1);
        return d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
      });

      new Chart(canvas, {
        type: 'line',
        data: {
          labels: fmtLabels,
          datasets: [lineDataset({
            values: values,
            color: c.accent,
            fillAlphaHex: '14',
            pointRadius: values.length <= 12 ? 4 : 2,
            tension: 0.35,
          })]
        },
        options: lineOptions({
          tooltip: gbpTooltip(0),
          extraScales: {
            y: { ticks: { color: c.muted, font: { size: 11 }, callback: function(v) { return '£' + (v >= 1000 ? (v/1000).toFixed(0) + 'k' : v); } } }
          }
        })
      });
    })();

    // ── 8. Overview Daily Portfolio Chart ────────────────────────────────────
    (function initDailyPortfolioChart() {
      var canvas = document.getElementById('dailyPortfolioChart');
      if (!canvas) return;
      var allLabels = JSON.parse(canvas.dataset.labels || '[]');
      var allValues = JSON.parse(canvas.dataset.values || '[]');
      var allContributions = JSON.parse(canvas.dataset.contributions || '[]');
      var fallbackValue = parseFloat(canvas.dataset.fallback || '0');
      var chart = null;

      // Derive the dates on which contributions actually landed (cumulative
      // jumps), so we can mark them on the chart when the user hovers the
      // contributions chip.
      var contribEventDates = {};
      for (var ci = 0; ci < allContributions.length; ci++) {
        var prevC = ci === 0 ? 0 : allContributions[ci - 1];
        if ((allContributions[ci] - prevC) > 0.005) {
          contribEventDates[allLabels[ci]] = true;
        }
      }

      var periods = { '1D': 1, '1M': 30, '6M': 180, '1Y': 365, 'ALL': 999999 };

      function parseYMD(dateStr) {
        if (!dateStr || typeof dateStr !== 'string') return null;
        var parts = dateStr.split('-');
        if (parts.length < 3) return null;
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      }

      // Format a local Date as YYYY-MM-DD using local components.
      // toISOString() would return UTC, which mismatches snapshot keys stored in
      // UK local time when the browser is in BST (off-by-one day).
      function formatYMD(d) {
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var dd = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + dd;
      }

      function ensureMinPoints(labels, values) {
        if (!labels.length) {
          var today = new Date();
          var yesterday = new Date(today.getTime() - 86400000);
          return {
            labels: [formatYMD(yesterday), formatYMD(today)],
            values: [fallbackValue, fallbackValue]
          };
        }
        if (labels.length === 1) {
          var dt = parseYMD(labels[0]) || new Date();
          var prev = new Date(dt.getTime() - 86400000);
          return {
            labels: [formatYMD(prev), labels[0]],
            values: [values[0], values[0]]
          };
        }
        return { labels: labels, values: values };
      }

      function buildSeries(period) {
        var src = ensureMinPoints(allLabels, allValues);
        var cutoffDays = periods[period] || 365;
        var today = new Date();
        var endDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        var cutoffDate = new Date(endDate.getTime() - cutoffDays * 24 * 60 * 60 * 1000);

        var points = [];
        for (var i = 0; i < src.labels.length; i++) {
          var dt = parseYMD(src.labels[i]);
          if (dt) points.push({ d: dt, s: src.labels[i], v: Number(src.values[i]) });
        }
        points.sort(function(a, b) { return a.d - b.d; });
        if (!points.length) return ensureMinPoints([], []);

        var startDate = points[0].d > cutoffDate ? points[0].d : cutoffDate;
        var labels = [], values = [];

        if (cutoffDays <= 400) {
          var map = {};
          points.forEach(function(p) { map[p.s] = p.v; });
          var lastV = fallbackValue;
          for (var k = 0; k < points.length; k++) {
            if (points[k].d < startDate) lastV = points[k].v; else break;
          }
          for (var cur = new Date(startDate); cur <= endDate; cur.setDate(cur.getDate() + 1)) {
            var s = formatYMD(cur);
            if (map.hasOwnProperty(s)) lastV = map[s];
            labels.push(s); values.push(lastV);
          }
        } else {
          points.forEach(function(p) {
            if (p.d >= startDate && p.d <= endDate) { labels.push(p.s); values.push(p.v); }
          });
        }
        return ensureMinPoints(labels, values);
      }

      function updateChart(period) {
        var data = buildSeries(period);
        var fmtLabels = data.labels.map(function(s) {
          var d = parseYMD(s);
          return d ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : s;
        });

        var dataVals = data.values.filter(isFinite);
        var yMin = dataVals.length ? Math.min.apply(null, dataVals) : 0;
        var yMax = dataVals.length ? Math.max.apply(null, dataVals) : 1;
        var yRange = yMax - yMin;
        var kDec = (yMax > 0 && yRange / yMax < 0.005) ? 2 : (yMax > 0 && yRange / yMax < 0.05 ? 1 : 0);
        var yPad = yRange > 0 ? yRange * 0.25 : yMax * 0.01;

        function fmtTick(v) {
          return v >= 1000 ? '£' + (v / 1000).toFixed(kDec) + 'k' : '£' + Math.round(v);
        }

        if (typeof window.Chart === 'function') {
          if (chart) chart.destroy();
          var ctx = canvas.getContext('2d');
          var grad = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
          grad.addColorStop(0, c.accent + '55');
          grad.addColorStop(1, c.accent + '00');

          // Overlay dataset: dot at every contribution date in the current
          // slice. Hidden by default (pointRadius 0); revealed when the
          // contributions chip is hovered.
          var contribOverlay = data.labels.map(function (lbl, idx) {
            return contribEventDates[lbl] ? data.values[idx] : null;
          });

          chart = new Chart(ctx, {
            type: 'line',
            plugins: [crosshairPlugin],
            data: {
              labels: fmtLabels,
              datasets: [lineDataset({
                values: data.values,
                color: c.accent,
                backgroundColor: grad,
                pointCutoff: 30,
                tension: 0.25
              }), {
                data: contribOverlay,
                showLine: false,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointBackgroundColor: c.accent5,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointStyle: 'circle',
                borderColor: 'transparent',
                spanGaps: false
              }]
            },
            options: lineOptions({
              tooltip: polishedTooltip({
                title: function (items) {
                  var idx = items && items[0] ? items[0].dataIndex : -1;
                  var raw = idx >= 0 ? data.labels[idx] : '';
                  var d = parseYMD(raw);
                  return d ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : raw;
                },
                label: function (ctx2) {
                  return ' £' + ctx2.parsed.y.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
              }),
              extraScales: {
                y: { min: yMin - yPad, max: yMax + yPad, ticks: { color: c.muted, font: { size: 11 }, callback: fmtTick } }
              },
              extra: { interaction: { mode: 'index', intersect: false } }
            })
          });
        } else {
          drawFallback(canvas, data.values, c.accent);
        }

        // Stats
        if (data.values.length) {
          var latest = data.values[data.values.length - 1];
          var first = data.values[0];
          var diff = latest - first;
          var pct = first ? (diff / first * 100) : null;
          var lEl = document.getElementById('latestValue');
          var cEl = document.getElementById('changeValue');
          var labelEl = document.getElementById('changeLabel');
          var breakdownEl = document.getElementById('changeBreakdown');
          if (lEl) lEl.textContent = '£' + latest.toLocaleString('en-GB', { minimumFractionDigits: 2 });
          if (cEl) {
            cEl.textContent = (diff >= 0 ? '+' : '') + diff.toLocaleString('en-GB', { minimumFractionDigits: 2 }) +
              (pct !== null ? ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%)' : '');
            cEl.style.color = diff >= 0 ? 'var(--success)' : 'var(--danger)';
          }
          if (labelEl) {
            var firstDate = parseYMD(data.labels[0]);
            labelEl.textContent = firstDate
              ? 'Change since ' + firstDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
              : 'Change';
          }
          if (breakdownEl) {
            var contribDelta = null;
            if (allContributions.length === allLabels.length && data.labels.length) {
              var startIdx = allLabels.indexOf(data.labels[0]);
              var endIdx = allLabels.indexOf(data.labels[data.labels.length - 1]);
              if (startIdx >= 0 && endIdx >= 0) {
                contribDelta = (allContributions[endIdx] || 0) - (allContributions[startIdx] || 0);
              }
            }
            if (contribDelta !== null) {
              var marketGain = diff - contribDelta;
              var marketPct = first ? (marketGain / first * 100) : null;
              var fmt = function (n) {
                return (n >= 0 ? '+£' : '−£') + Math.abs(n).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
              };
              var marketCls = marketGain >= 0 ? 'change-chip-market-pos' : 'change-chip-market-neg';
              var pctText = (marketPct !== null)
                ? ' (' + (marketPct >= 0 ? '+' : '') + marketPct.toFixed(2) + '%)'
                : '';
              breakdownEl.innerHTML =
                '<span class="change-chip change-chip-contrib">' +
                  fmt(contribDelta) + '<span class="change-chip-label">contributions</span>' +
                '</span>' +
                '<span class="change-chip ' + marketCls + '">' +
                  fmt(marketGain) + '<span class="change-chip-label">market' + pctText + '</span>' +
                '</span>';

              // Hovering the contributions chip reveals dots on the chart at
              // the dates contributions actually landed.
              var contribChip = breakdownEl.querySelector('.change-chip-contrib');
              if (contribChip && chart && chart.data.datasets[1]) {
                contribChip.addEventListener('mouseenter', function () {
                  if (!chart || !chart.data.datasets[1]) return;
                  chart.data.datasets[1].pointRadius = 6;
                  chart.update('none');
                });
                contribChip.addEventListener('mouseleave', function () {
                  if (!chart || !chart.data.datasets[1]) return;
                  chart.data.datasets[1].pointRadius = 0;
                  chart.update('none');
                });
              }
            } else {
              breakdownEl.innerHTML = '<span class="helper-text">Includes market growth + any contributions you made during this period.</span>';
            }
          }
        }
      }

      document.querySelectorAll('.period-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.preventDefault();
          document.querySelectorAll('.period-btn').forEach(function(b) { b.classList.remove('active'); });
          this.classList.add('active');
          updateChart(this.dataset.period);
        });
      });

      updateChart('ALL');
    })();
  });

  /* Helpers for Doughnut interactions */
  function highlightAllocList(idx, colors) {
    var items = document.querySelectorAll('.allocation-item[data-index]');
    items.forEach(function(item) {
      var i = parseInt(item.dataset.index);
      var dot = item.querySelector('.alloc-dot');
      if (idx >= 0 && i === idx) {
        var col = colors[i % colors.length];
        item.style.borderColor = col;
        item.style.boxShadow   = '0 0 0 1px ' + col + '55, 0 4px 22px ' + col + '30';
        item.style.transform   = 'translateX(4px)';
        if (dot) dot.style.boxShadow = '0 0 7px 2px ' + col + '99';
      } else {
        item.style.borderColor = '';
        item.style.boxShadow   = '';
        item.style.transform   = '';
        if (dot) dot.style.boxShadow = '';
      }
    });
  }

  /* Fallback canvas drawing when Chart.js fails */
  function drawFallback(canvas, values, color) {
    var ctx = canvas.getContext('2d');
    var rect = canvas.getBoundingClientRect();
    var w = Math.max(1, Math.floor(rect.width));
    var h = Math.max(1, Math.floor(rect.height));
    var dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var padL = 44, padR = 12, padT = 10, padB = 22;
    var innerW = Math.max(1, w - padL - padR);
    var innerH = Math.max(1, h - padT - padB);

    var minV = Infinity, maxV = -Infinity;
    for (var i = 0; i < values.length; i++) {
      var v = Number(values[i]);
      if (!isFinite(v)) continue;
      if (v < minV) minV = v; if (v > maxV) maxV = v;
    }
    if (!isFinite(minV) || !isFinite(maxV)) return;
    if (minV === maxV) { minV = minV * 0.999; maxV = maxV * 1.001; }

    function xFor(idx) { return values.length <= 1 ? padL + innerW / 2 : padL + (idx / (values.length - 1)) * innerW; }
    function yFor(val) { return padT + (1 - (val - minV) / (maxV - minV)) * innerH; }

    ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (var g = 0; g <= 4; g++) {
      var y = padT + (g / 4) * innerH;
      ctx.moveTo(padL, y); ctx.lineTo(padL + innerW, y);
    }
    ctx.stroke();

    ctx.beginPath();
    for (var p = 0; p < values.length; p++) {
      var pv = Number(values[p]); if (!isFinite(pv)) continue;
      var px = xFor(p), py = yFor(pv);
      if (p === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.lineWidth = 2; ctx.strokeStyle = color; ctx.stroke();
  }

  global.ChartHelpers = {
    colors: colors,
    gbpTooltip: gbpTooltip,
    lineOptions: lineOptions,
    lineDataset: lineDataset,
    crosshairPlugin: crosshairPlugin,
    polishedTooltip: polishedTooltip,
  };
})(window);
