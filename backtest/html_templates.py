from typing import Any


def render_positions_html(
    chart_title: str,
    plotly_cdn: str,
    x_json: str,
    y_json: str,
    y2_json: str,
    has_y2: bool,
    stats_html: str,
    ret_x_json: str,
    ret_y_json: str,
    has_returns: bool,
) -> str:
    has_y2_js = "true" if has_y2 else "false"
    has_returns_js = "true" if has_returns else "false"
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{chart_title}</title>
  <script src=\"{plotly_cdn}\"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Fira Sans', 'Droid Sans', 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; }}
    #chart {{ width: 100%; height: 60vh; }}
    #returnsChart {{ width: 100%; height: 35vh; }}
    .container {{ padding: 12px 16px; }}
    h1 {{ font-size: 18px; margin: 8px 0 8px 0; }}
    h2 {{ font-size: 16px; margin: 12px 0 6px 0; }}
    p {{ color: #555; margin: 4px 0 12px 0; }}
    table.stats {{ border-collapse: collapse; margin: 8px 0 12px 0; }}
    table.stats td, table.stats th {{ border: 1px solid #ddd; padding: 6px 10px; }}
    table.stats th {{ background: #f7f7f7; text-align: left; }}
  </style>
  </head>
<body>
  <div class=\"container\">
    <h1>{chart_title}</h1>
    <p>Includes secondary axis for number of positions held per day.</p>
  </div>
  <div id=\"chart\"></div>
  <div class=\"container\">
    <h2>Daily Returns</h2>
  </div>
  <div id=\"returnsChart\"></div>
  <div class=\"container\">
    <h2>Summary Statistics</h2>
    {stats_html}
  </div>
  <script>
    const x = {x_json};
    const y = {y_json};
    const y2 = {y2_json};
    const rx = {ret_x_json};
    const ry = {ret_y_json};
    const traces = [];
    traces.push({{
      x: x,
      y: y,
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Total Position Value',
      line: {{ color: '#1f77b4', width: 2 }},
      marker: {{ size: 4 }}
    }});
    if ({has_y2_js}) {{
      traces.push({{
        x: x,
        y: y2,
        type: 'bar',
        name: 'Position Count',
        yaxis: 'y2',
        marker: {{ color: 'rgba(255,127,14,0.5)' }}
      }});
    }}
    const layout = {{
      margin: {{ t: 30, r: 20, b: 40, l: 60 }},
      legend: {{ orientation: 'h', x: 0, y: 1.1 }},
      xaxis: {{ title: 'Date', type: 'date', rangeslider: {{ visible: true }} }},
      yaxis: {{ title: 'Market Value', separatethousands: true, tickprefix: '$' }},
      yaxis2: {{ title: 'Positions', overlaying: 'y', side: 'right', rangemode: 'tozero' }},
    }};
    Plotly.newPlot('chart', traces, layout, {{ responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d'] }});

    if ({has_returns_js}) {{
      const retTraces = [{{
        x: rx,
        y: ry,
        type: 'scatter',
        mode: 'lines',
        name: 'Daily Return',
        line: {{ color: '#2ca02c', width: 1.8 }}
      }}];
      const retLayout = {{
        margin: {{ t: 10, r: 20, b: 40, l: 60 }},
        xaxis: {{ title: 'Date', type: 'date' }},
        yaxis: {{ title: 'Daily Return', tickformat: '.2%', rangemode: 'tozero' }},
      }};
      Plotly.newPlot('returnsChart', retTraces, retLayout, {{ responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d'] }});
    }}
  </script>
</body>
</html>
"""


