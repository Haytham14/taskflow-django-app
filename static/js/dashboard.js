document.addEventListener("DOMContentLoaded", function () {
  function readJson(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : [];
  }

  const statusLabels = readJson("status-labels");
  const statusData = readJson("status-data");
  const priorityLabels = readJson("priority-labels");
  const priorityData = readJson("priority-data");

  const fontFamily = "Roboto, system-ui, sans-serif";
  const chartText = "#9299A5";
  const chartGrid = "rgba(255, 255, 255, 0.10)";
  const chartSurface = "#171B21";

  const statusCtx = document.getElementById("statusChart");
  if (statusCtx && window.Chart) {
    new Chart(statusCtx, {
      type: "doughnut",
      data: {
        labels: statusLabels,
        datasets: [
          {
            data: statusData,
            backgroundColor: ["#234B98", "#356DE0", "#7898DE", "#5C8A66"],
            borderColor: chartSurface,
            borderWidth: 3,
            hoverOffset: 2,
          },
        ],
      },
      options: {
        cutout: "68%",
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 12, color: chartText, font: { family: fontFamily } },
          },
        },
      },
    });
  }

  const priorityCtx = document.getElementById("priorityChart");
  if (priorityCtx && window.Chart) {
    new Chart(priorityCtx, {
      type: "bar",
      data: {
        labels: priorityLabels,
        datasets: [
          {
            data: priorityData,
            backgroundColor: ["#5C8A66", "#D9A441", "#E1553D", "#9B2D20"],
            borderRadius: 6,
            maxBarThickness: 56,
          },
        ],
      },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { color: chartText, precision: 0, font: { family: fontFamily } },
            grid: { color: chartGrid },
          },
          y: {
            ticks: { color: chartText, font: { family: fontFamily } },
            grid: { display: false },
          },
        },
      },
    });
  }
});
