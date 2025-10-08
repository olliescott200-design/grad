document.addEventListener('DOMContentLoaded', function() {
  var select = document.getElementById('storyTheme');
  
  if (!select) return;
  
  select.addEventListener('change', function() {
    var selectedValue = this.value;
    
    // Hide all theme sections
    var allSections = document.querySelectorAll('.theme-section');
    for (var i = 0; i < allSections.length; i++) {
      allSections[i].style.display = 'none';
    }
    
    // Toggle placeholder message
    var placeholder = document.getElementById('selectThemeMessage');
    if (placeholder) {
      placeholder.style.display = selectedValue ? 'none' : 'block';
    }
    
    // Show selected theme section
    if (selectedValue) {
      var targetSection = document.getElementById('theme-' + selectedValue);
      if (targetSection) {
        targetSection.style.display = 'block';
        // Scroll to it
        setTimeout(function() {
          targetSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 100);
      }
    }
  });
});
