interface FileList {
  readonly length: number;
  item(index: number): File | null;
  [index: number]: File;
}
