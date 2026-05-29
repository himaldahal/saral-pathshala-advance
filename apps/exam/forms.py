"""
exams/forms.py
──────────────
TinyMCE-powered forms used by the Django admin.
"""
from django import forms
from tinymce.widgets import TinyMCE

from .models import Exam, Section, Paragraph, Question

# ─────────────────────────────────────────────────────────────────────────────
# Shared TinyMCE config
# ─────────────────────────────────────────────────────────────────────────────

_FULL = {
    'height': 320,
    'menubar': False,
    'plugins': (
        'advlist autolink lists link image charmap preview '
        'anchor searchreplace visualblocks code fullscreen '
        'insertdatetime media table codesample'
    ),
    'toolbar': (
        'undo redo | styles | bold italic underline | '
        'alignleft aligncenter alignright | '
        'bullist numlist | outdent indent | '
        'codesample | link image | code | fullscreen'
    ),
    'codesample_global_prismjs': True,
    'codesample_languages': [
        {'text': 'Python',     'value': 'python'},
        {'text': 'JavaScript', 'value': 'javascript'},
        {'text': 'C',          'value': 'c'},
        {'text': 'C++',        'value': 'cpp'},
        {'text': 'Java',       'value': 'java'},
        {'text': 'SQL',        'value': 'sql'},
        {'text': 'Bash',       'value': 'bash'},
    ],
    # Tell TinyMCE not to strip math delimiters
    'extended_valid_elements': 'span[*]',
    'valid_children': '+body[style]',
}

_COMPACT = {**_FULL, 'height': 180}


def _mce(cfg=_FULL, **attrs):
    return TinyMCE(mce_attrs=cfg, attrs=attrs)


# ─────────────────────────────────────────────────────────────────────────────
# Exam admin form
# ─────────────────────────────────────────────────────────────────────────────

class ExamAdminForm(forms.ModelForm):
    description  = forms.CharField(widget=_mce(), required=False, label='Description')
    instructions = forms.CharField(widget=_mce(), required=False, label='Instructions')

    class Meta:
        model  = Exam
        fields = '__all__'


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph admin form
# ─────────────────────────────────────────────────────────────────────────────

class ParagraphAdminForm(forms.ModelForm):
    content = forms.CharField(widget=_mce(), label='Paragraph Content')

    class Meta:
        model  = Paragraph
        fields = '__all__'


# ─────────────────────────────────────────────────────────────────────────────
# Question admin form
# ─────────────────────────────────────────────────────────────────────────────

class QuestionAdminForm(forms.ModelForm):
    question_text = forms.CharField(widget=_mce(),          label='Question')
    option_one    = forms.CharField(widget=_mce(_COMPACT),  label='Option 1', required=False)
    option_two    = forms.CharField(widget=_mce(_COMPACT),  label='Option 2', required=False)
    option_three  = forms.CharField(widget=_mce(_COMPACT),  label='Option 3', required=False)
    option_four   = forms.CharField(widget=_mce(_COMPACT),  label='Option 4', required=False)
    explanation   = forms.CharField(widget=_mce(_COMPACT),  label='Explanation', required=False)

    class Meta:
        model  = Question
        fields = '__all__'