"""
Benchmark Report Generator

Generates comparison reports in various formats.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

from metrics import BenchmarkResults


def generate_comparison_report(results: Dict[str, BenchmarkResults], output_dir: str) -> str:
    """Generate HTML comparison report"""
    os.makedirs(output_dir, exist_ok=True)

    native = results.get("native")
    clove = results.get("clove")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f"report_{timestamp}.html")

    html = generate_html_report(native, clove)

    with open(report_path, 'w') as f:
        f.write(html)

    return report_path


def generate_html_report(native: Optional[BenchmarkResults], clove: Optional[BenchmarkResults]) -> str:
    """Generate HTML content for report"""

    # Collect data for charts
    tasks = set()
    if native:
        tasks.update(native.statistics.keys())
    if clove:
        tasks.update(clove.statistics.keys())

    tasks = sorted(tasks)

    native_data = []
    clove_data = []
    overhead_data = []

    for task in tasks:
        native_mean = native.statistics.get(task, {}).get("mean_ms", 0) if native else 0
        clove_mean = clove.statistics.get(task, {}).get("mean_ms", 0) if clove else 0

        native_data.append(native_mean)
        clove_data.append(clove_mean)

        if native_mean > 0:
            overhead = ((clove_mean - native_mean) / native_mean) * 100
        else:
            overhead = 0
        overhead_data.append(overhead)

    # Pre-compute summary values to avoid f-string issues
    native_iterations = sum(native.statistics.get(t, {}).get("count", 0) for t in tasks) if native else 0
    clove_iterations = sum(clove.statistics.get(t, {}).get("count", 0) for t in tasks) if clove else 0
    avg_overhead = sum(overhead_data) / len(overhead_data) if overhead_data else 0

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clove Benchmark Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 2rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 0.5rem;
            font-size: 2.5rem;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 2rem;
        }}
        .card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .card h2 {{
            margin-bottom: 1rem;
            color: #00d2ff;
            font-size: 1.3rem;
        }}
        .chart-container {{
            position: relative;
            height: 400px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        th {{
            background: rgba(0,210,255,0.1);
            font-weight: 600;
        }}
        tr:hover {{
            background: rgba(255,255,255,0.03);
        }}
        .positive {{
            color: #ff6b6b;
        }}
        .negative {{
            color: #51cf66;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .summary-item {{
            background: rgba(0,210,255,0.1);
            padding: 1rem;
            border-radius: 12px;
            text-align: center;
        }}
        .summary-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #00d2ff;
        }}
        .summary-label {{
            font-size: 0.85rem;
            color: #888;
            margin-top: 0.25rem;
        }}
        .footer {{
            text-align: center;
            color: #666;
            margin-top: 2rem;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Clove Benchmark Report</h1>
        <p class="subtitle">Native Python vs Clove Kernel Execution</p>

        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">{len(tasks)}</div>
                <div class="summary-label">Tasks Benchmarked</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{native_iterations}</div>
                <div class="summary-label">Native Iterations</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{clove_iterations}</div>
                <div class="summary-label">Clove Iterations</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{avg_overhead:+.1f}%</div>
                <div class="summary-label">Avg Overhead</div>
            </div>
        </div>

        <div class="card">
            <h2>Latency Comparison (ms)</h2>
            <div class="chart-container">
                <canvas id="latencyChart"></canvas>
            </div>
        </div>

        <div class="card">
            <h2>Overhead Analysis (%)</h2>
            <div class="chart-container">
                <canvas id="overheadChart"></canvas>
            </div>
        </div>

        <div class="card">
            <h2>Detailed Results</h2>
            <table>
                <thead>
                    <tr>
                        <th>Task</th>
                        <th>Native (ms)</th>
                        <th>Clove (ms)</th>
                        <th>Overhead</th>
                        <th>Native P95</th>
                        <th>Clove P95</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(generate_table_rows(native, clove, tasks))}
                </tbody>
            </table>
        </div>

        <div class="footer">
            Generated by Clove Benchmark Framework | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>

    <script>
        // Latency Chart
        new Chart(document.getElementById('latencyChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(tasks)},
                datasets: [
                    {{
                        label: 'Native',
                        data: {json.dumps(native_data)},
                        backgroundColor: 'rgba(81, 207, 102, 0.7)',
                        borderColor: 'rgba(81, 207, 102, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Clove',
                        data: {json.dumps(clove_data)},
                        backgroundColor: 'rgba(0, 210, 255, 0.7)',
                        borderColor: 'rgba(0, 210, 255, 1)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: 'Latency (ms)',
                            color: '#888'
                        }},
                        grid: {{
                            color: 'rgba(255,255,255,0.1)'
                        }},
                        ticks: {{ color: '#888' }}
                    }},
                    x: {{
                        grid: {{
                            color: 'rgba(255,255,255,0.1)'
                        }},
                        ticks: {{ color: '#888' }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        labels: {{ color: '#eee' }}
                    }}
                }}
            }}
        }});

        // Overhead Chart
        new Chart(document.getElementById('overheadChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(tasks)},
                datasets: [{{
                    label: 'Overhead %',
                    data: {json.dumps(overhead_data)},
                    backgroundColor: {json.dumps(['rgba(255, 107, 107, 0.7)' if o > 0 else 'rgba(81, 207, 102, 0.7)' for o in overhead_data])},
                    borderColor: {json.dumps(['rgba(255, 107, 107, 1)' if o > 0 else 'rgba(81, 207, 102, 1)' for o in overhead_data])},
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        title: {{
                            display: true,
                            text: 'Overhead (%)',
                            color: '#888'
                        }},
                        grid: {{
                            color: 'rgba(255,255,255,0.1)'
                        }},
                        ticks: {{ color: '#888' }}
                    }},
                    x: {{
                        grid: {{
                            color: 'rgba(255,255,255,0.1)'
                        }},
                        ticks: {{ color: '#888' }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>'''

    return html


def generate_table_rows(native: Optional[BenchmarkResults], clove: Optional[BenchmarkResults], tasks: list) -> list:
    """Generate HTML table rows for detailed results"""
    rows = []

    for task in tasks:
        native_stats = native.statistics.get(task, {}) if native else {}
        clove_stats = clove.statistics.get(task, {}) if clove else {}

        native_mean = native_stats.get("mean_ms", 0)
        clove_mean = clove_stats.get("mean_ms", 0)
        native_p95 = native_stats.get("p95_ms", 0)
        clove_p95 = clove_stats.get("p95_ms", 0)

        if native_mean > 0:
            overhead = ((clove_mean - native_mean) / native_mean) * 100
            overhead_class = "positive" if overhead > 0 else "negative"
            overhead_str = f'<span class="{overhead_class}">{overhead:+.1f}%</span>'
        else:
            overhead_str = "N/A"

        rows.append(f'''
            <tr>
                <td>{task}</td>
                <td>{native_mean:.2f}</td>
                <td>{clove_mean:.2f}</td>
                <td>{overhead_str}</td>
                <td>{native_p95:.2f}</td>
                <td>{clove_p95:.2f}</td>
            </tr>
        ''')

    return rows


def generate_markdown_report(native: Optional[BenchmarkResults], clove: Optional[BenchmarkResults]) -> str:
    """Generate Markdown report"""
    lines = [
        "# Clove Benchmark Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        "| Task | Native (ms) | Clove (ms) | Overhead |",
        "|------|-------------|------------|----------|",
    ]

    tasks = set()
    if native:
        tasks.update(native.statistics.keys())
    if clove:
        tasks.update(clove.statistics.keys())

    for task in sorted(tasks):
        native_mean = native.statistics.get(task, {}).get("mean_ms", 0) if native else 0
        clove_mean = clove.statistics.get(task, {}).get("mean_ms", 0) if clove else 0

        if native_mean > 0:
            overhead = ((clove_mean - native_mean) / native_mean) * 100
            overhead_str = f"{overhead:+.1f}%"
        else:
            overhead_str = "N/A"

        lines.append(f"| {task} | {native_mean:.2f} | {clove_mean:.2f} | {overhead_str} |")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test report generation
    print("Report generator module loaded successfully")
