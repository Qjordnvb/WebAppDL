# core/forms.py
from django import forms
import json

class StartSessionForm(forms.Form):
    url = forms.URLField(
        max_length=2000,
        required=True,
        label="URL del Sitio Web",
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://ejemplo.com'})
    )
    reference_schema = forms.CharField(
        required=True,
        label="Contenido JSON de Referencia/Schema",  # <-- Etiqueta actualizada (opcional)
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 10}),
        help_text="Pega aquí el contenido completo del archivo JSON de DataLayers esperados o el schema.",
    )
    description = forms.CharField(
        required=False,
        label="Descripción (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Validación básica del JSON
    def clean_reference_schema(self):
        content = self.cleaned_data["reference_schema"]
        try:
            # Intenta parsear para validar formato JSON básico
            json.loads(content)
        except json.JSONDecodeError:
            raise forms.ValidationError(
                "El contenido introducido no es un JSON válido."
            )
        # Podrías añadir validación del schema aquí si quisieras usando jsonschema
        return content
