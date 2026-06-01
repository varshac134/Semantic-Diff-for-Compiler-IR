; ModuleID = 'old'
source_filename = "old.c"

define i32 @add_one(i32 %x) {
entry:
  %0 = add nsw i32 %x, 1
  ret i32 %0
}

define i32 @main() {
entry:
  %value = alloca i32, align 4
  %result = alloca i32, align 4
  store i32 42, i32* %value, align 4
  %1 = load i32, i32* %value, align 4
  %2 = call i32 @add_one(i32 %1)
  store i32 %2, i32* %result, align 4
  %3 = load i32, i32* %result, align 4
  call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([9 x i8], [9 x i8]* @.str, i32 0, i32 0), i32 %3)
  ret i32 0
}

declare i32 @printf(i8*, ...)

@.str = private unnamed_addr constant [9 x i8] c"result=%d\0A\00", align 1
