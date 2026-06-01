#include <stdio.h>

int add_one(int x) {
    return x + 1;
}

int main(void) {
    int value = 42;
    int result = add_one(value);
    printf("result=%d\n", result);
    return 0;
}
