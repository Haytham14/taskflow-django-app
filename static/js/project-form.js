document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".project-member-picker").forEach(function (picker) {
    const select = picker.querySelector("select[multiple]");
    const search = picker.querySelector('input[type="search"]');
    const chips = picker.querySelector(".selected-member-chips");
    const list = picker.querySelector(".member-option-list");
    if (!select || !search || !chips || !list) return;

    function initials(name) {
      return name
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map(function (part) {
          return part.charAt(0).toUpperCase();
        })
        .join("") || "?";
    }

    function optionData() {
      return Array.from(select.options).map(function (option) {
        return {
          option: option,
          id: option.value,
          name: option.textContent.trim(),
          selected: option.selected,
        };
      });
    }

    function setSelected(option, selected) {
      option.selected = selected;
      render();
    }

    function renderChips(items) {
      chips.innerHTML = "";
      items.filter(function (item) { return item.selected; }).forEach(function (item) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "selected-member-chip";
        chip.innerHTML = '<span>' + initials(item.name) + '</span><strong></strong><em aria-hidden="true">×</em>';
        chip.querySelector("strong").textContent = item.name;
        chip.addEventListener("click", function () {
          setSelected(item.option, false);
        });
        chips.appendChild(chip);
      });
    }

    function renderList(items) {
      const query = search.value.trim().toLowerCase();
      list.innerHTML = "";

      items
        .filter(function (item) {
          return !query || item.name.toLowerCase().includes(query);
        })
        .forEach(function (item) {
          const row = document.createElement("button");
          row.type = "button";
          row.className = "member-option-row" + (item.selected ? " selected" : "");
          row.innerHTML = '<span class="member-initials"></span><strong></strong><small>Membre</small><em aria-hidden="true"></em>';
          row.querySelector(".member-initials").textContent = initials(item.name);
          row.querySelector("strong").textContent = item.name;
          row.querySelector("em").textContent = item.selected ? "✓" : "+";
          row.addEventListener("click", function () {
            setSelected(item.option, !item.option.selected);
          });
          list.appendChild(row);
        });

      if (!list.children.length) {
        const empty = document.createElement("p");
        empty.className = "member-option-empty";
        empty.textContent = "Aucun membre trouvé.";
        list.appendChild(empty);
      }
    }

    function render() {
      const items = optionData();
      renderChips(items);
      renderList(items);
    }

    search.addEventListener("input", render);
    render();
  });
});
