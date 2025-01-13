from django.contrib import admin
from .models import ChatHistory, PromptTemplate, Tool

admin.site.register(ChatHistory)
admin.site.register(PromptTemplate)
admin.site.register(Tool)
