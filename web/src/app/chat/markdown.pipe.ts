import { Pipe, PipeTransform } from '@angular/core';
import { marked } from 'marked';

/**
 * Renders assistant markdown to HTML. Binding the result via [innerHTML]
 * passes it through Angular's built-in sanitizer, which strips scripts and
 * event handlers.
 */
@Pipe({ name: 'markdown' })
export class MarkdownPipe implements PipeTransform {
  transform(value: string): string {
    return marked.parse(value, { async: false });
  }
}
