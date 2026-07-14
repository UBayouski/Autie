import {
  Component,
  ElementRef,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

@Component({
  selector: 'app-composer',
  templateUrl: './composer.html',
  styleUrl: './composer.css',
})
export class ComposerComponent {
  readonly disabled = input(false);
  readonly send = output<string>();

  protected readonly draft = signal('');

  private readonly textarea =
    viewChild.required<ElementRef<HTMLTextAreaElement>>('box');

  protected onInput(event: Event): void {
    const el = event.target as HTMLTextAreaElement;
    this.draft.set(el.value);
    this.autoGrow(el);
  }

  private autoGrow(el: HTMLTextAreaElement): void {
    // Grow with content up to the CSS max-height, then scroll inside.
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  protected submit(): void {
    const text = this.draft().trim();
    if (!text || this.disabled()) {
      return;
    }
    this.send.emit(text);
    this.draft.set('');
    const el = this.textarea().nativeElement;
    el.value = '';
    el.style.height = 'auto';
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submit();
    }
  }
}
