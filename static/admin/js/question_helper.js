document.addEventListener('DOMContentLoaded', function() {
    const examSelect = document.getElementById('id_exam');
    const sectionSelect = document.getElementById('id_section');
    const paragraphSelect = document.getElementById('id_paragraph');

    if (!examSelect || !sectionSelect || !paragraphSelect) {
        return; // Not on the right page or elements missing
    }

    // Function to populate a dropdown
    function populateSelect(selectElement, items, selectedValue, emptyText = '---------') {
        // Clear all except the first option
        selectElement.innerHTML = '';
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = emptyText;
        selectElement.appendChild(emptyOpt);

        items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.id;
            opt.textContent = item.title || item.name || `ID: ${item.id}`;
            if (String(item.id) === String(selectedValue)) {
                opt.selected = true;
            }
            selectElement.appendChild(opt);
        });
    }

    // Function to fetch and update dropdowns
    async function updateDropdowns(examId, initialSecId = null, initialParaId = null) {
        if (!examId) {
            populateSelect(sectionSelect, [], null);
            populateSelect(paragraphSelect, [], null);
            return;
        }

        try {
            const response = await fetch(`/dhokakhol-custom/api/get-sections-paragraphs/?exam_id=${examId}`);
            if (!response.ok) throw new Error('API fetch failed');
            const data = await response.json();

            // Store current selection if not overriding
            const currentSecVal = initialSecId !== null ? initialSecId : sectionSelect.value;
            const currentParaVal = initialParaId !== null ? initialParaId : paragraphSelect.value;

            // Populate Section Select
            populateSelect(sectionSelect, data.sections, currentSecVal);

            // Populate Paragraph Select
            populateSelect(paragraphSelect, data.paragraphs, currentParaVal);

            // Add change listener to Section to filter Paragraphs locally if needed,
            // or we can just list paragraphs belonging to the selected section.
            // Let's filter paragraphs based on selected section.
            function filterParagraphs() {
                const selectedSectionId = sectionSelect.value;
                const filteredParas = data.paragraphs.filter(p => {
                    return !selectedSectionId || String(p.section_id) === String(selectedSectionId);
                });
                const activeParaVal = paragraphSelect.value;
                populateSelect(paragraphSelect, filteredParas, activeParaVal);
            }

            sectionSelect.addEventListener('change', filterParagraphs);
            // Run once initially
            filterParagraphs();

        } catch (error) {
            console.error('Error updating exam child dropdowns:', error);
        }
    }

    // Load initial data
    const initialExamId = examSelect.value;
    if (initialExamId) {
        updateDropdowns(initialExamId, sectionSelect.value, paragraphSelect.value);
    }

    // Bind change listener
    examSelect.addEventListener('change', function() {
        updateDropdowns(this.value, null, null);
    });
});
