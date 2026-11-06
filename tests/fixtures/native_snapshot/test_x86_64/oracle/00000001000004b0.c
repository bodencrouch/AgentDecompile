
undefined8 entry(void)

{
  uint uVar1;
  
  _printf("ReVa Test Program\n");
  uVar1 = _add(2,3);
  _printf("2 + 3 = %d\n",(ulong)uVar1);
  uVar1 = _multiply(4,5);
  _printf("4 * 5 = %d\n",(ulong)uVar1);
  return 0;
}

