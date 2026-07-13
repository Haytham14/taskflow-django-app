document.addEventListener("DOMContentLoaded", () => {
  const applicationSelect = document.getElementById("id_habilitation");
  const habilitationContainer = document.querySelector("[data-request-habilitations]");
  const accessTypeContainer = document.querySelector("[data-request-access-type]");

  if (!applicationSelect || !habilitationContainer || !accessTypeContainer) return;

  const accessTypeSelect = accessTypeContainer.querySelector("select");

  const renderHabilitations = (items) => {
    if (!items.length) {
      habilitationContainer.innerHTML = '<p class="help-text">Aucune habilitation disponible.</p>';
      return;
    }
    habilitationContainer.replaceChildren();
    items.forEach((item) => {
      const label = document.createElement("label");
      label.className = "request-option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "requested_habilitations";
      input.value = item.id;
      const text = document.createElement("span");
      text.textContent = item.name;
      label.append(input, text);
      habilitationContainer.appendChild(label);
    });
  };

  const renderAccessTypes = (items) => {
    accessTypeSelect.innerHTML = '<option value="">---------</option>';
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name;
      accessTypeSelect.appendChild(option);
    });
  };

  const loadApplicationOptions = async () => {
    const applicationId = applicationSelect.value;
    if (!applicationId) {
      renderHabilitations([]);
      renderAccessTypes([]);
      return;
    }

    try {
      const response = await fetch(`/api/habilitations/${applicationId}/`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Chargement impossible");
      const data = await response.json();
      renderHabilitations(data.habilitations || []);
      renderAccessTypes(data.access_types || []);
    } catch (_error) {
      habilitationContainer.innerHTML = '<p class="field-error">Impossible de charger les habilitations.</p>';
      renderAccessTypes([]);
    }
  };

  applicationSelect.addEventListener("change", loadApplicationOptions);
});
