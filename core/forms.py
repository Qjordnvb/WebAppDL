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
    reference_json_content = forms.CharField(
        required=True,
        label="Contenido JSON de Referencia",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
        help_text="Pega aquí el contenido completo del archivo JSON de DataLayers esperados."
    )
    description = forms.CharField(
        required=False,
        label="Descripción (Opcional)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Validación básica del JSON
    def clean_reference_json_content(self):
        content = self.cleaned_data['reference_json_content']
        try:
            # Intenta parsear para validar formato
            # Podrías añadir validaciones más específicas aquí si es necesario
            json.loads(content)
        except json.JSONDecodeError:
            raise forms.ValidationError("El contenido introducido no es un JSON válido.")
        return content
